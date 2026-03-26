#!/usr/bin/env bash

# Copyright (c) 2021-2026 community-scripts ORG
# Author: thost96 (thost96) | michelroegl-brunner | MickLesk
# Modified: Imogen Labs — Agent Edition (non-interactive)
# License: MIT | https://github.com/community-scripts/ProxmoxVED/raw/main/LICENSE

# ==============================================================================
# Docker VM - Creates a Docker-ready Virtual Machine
# Agent Edition: fully non-interactive. All settings via env vars or defaults.
#
# Environment variables (all optional, sensible defaults used):
#   PVE_VMID        - VM ID (default: next available)
#   PVE_HOSTNAME    - Hostname (default: docker)
#   PVE_CPU         - CPU cores (default: 2)
#   PVE_RAM         - RAM in MB (default: 4096)
#   PVE_DISK        - Disk size e.g. "20G" (default: 10G)
#   PVE_BRIDGE      - Network bridge (default: vmbr0)
#   PVE_STORAGE     - Storage pool (default: auto-detect first available)
#   PVE_OS          - OS choice: debian13, debian12, ubuntu2404, ubuntu2204 (default: debian13)
#   PVE_CLOUD_INIT  - yes/no (default: no for debian, yes for ubuntu)
#   PVE_START       - Start VM when done: yes/no (default: yes)
#   PVE_MAC         - MAC address (default: random)
#   PVE_VLAN        - VLAN tag (default: none)
#   PVE_MTU         - MTU size (default: none)
#   PVE_SSH_KEY     - SSH public key to inject (optional)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/misc/api.func" 2>/dev/null || true
source "${SCRIPT_DIR}/misc/vm-core.func" 2>/dev/null || true
source "${SCRIPT_DIR}/misc/cloud-init.func" 2>/dev/null || true
load_functions 2>/dev/null || true

# ==============================================================================
# SCRIPT VARIABLES
# ==============================================================================
APP="Docker"
APP_TYPE="vm"
NSAPP="docker-vm"
var_os="debian"
var_version="13"

GEN_MAC=02:$(openssl rand -hex 5 | awk '{print toupper($0)}' | sed 's/\(..\)/\1:/g; s/.$//')
RANDOM_UUID="$(cat /proc/sys/kernel/random/uuid)"
THIN="discard=on,ssd=1,"

# ==============================================================================
# ERROR HANDLING & CLEANUP
# ==============================================================================
set -e
trap 'error_handler $LINENO "$BASH_COMMAND"' ERR
trap cleanup EXIT
trap 'post_update_to_api "failed" "130"' SIGINT
trap 'post_update_to_api "failed" "143"' SIGTERM
trap 'post_update_to_api "failed" "129"; exit 129' SIGHUP

function error_handler() {
  local exit_code="$?"
  local line_number="$1"
  local command="$2"
  local error_message="${RD}[ERROR]${CL} in line ${RD}$line_number${CL}: exit code ${RD}$exit_code${CL}: while executing command ${YW}$command${CL}"
  post_update_to_api "failed" "${exit_code}"
  echo -e "\n$error_message\n"
  cleanup_vmid
}

# ==============================================================================
# OS SELECTION (non-interactive)
# ==============================================================================
function select_os() {
  local os_choice="${PVE_OS:-debian13}"
  case $os_choice in
  debian13)
    OS_TYPE="debian"
    OS_VERSION="13"
    OS_CODENAME="trixie"
    OS_DISPLAY="Debian 13 (Trixie)"
    ;;
  debian12)
    OS_TYPE="debian"
    OS_VERSION="12"
    OS_CODENAME="bookworm"
    OS_DISPLAY="Debian 12 (Bookworm)"
    ;;
  ubuntu2404)
    OS_TYPE="ubuntu"
    OS_VERSION="24.04"
    OS_CODENAME="noble"
    OS_DISPLAY="Ubuntu 24.04 LTS"
    ;;
  ubuntu2204)
    OS_TYPE="ubuntu"
    OS_VERSION="22.04"
    OS_CODENAME="jammy"
    OS_DISPLAY="Ubuntu 22.04 LTS"
    ;;
  *)
    echo "ERROR: Unknown OS choice '$os_choice'. Use: debian13, debian12, ubuntu2404, ubuntu2204" >&2
    exit 1
    ;;
  esac
  echo -e "${OS:-}${BOLD:-}${DGN:-}Operating System: ${BGN:-}${OS_DISPLAY}${CL:-}"
}

function select_cloud_init() {
  if [ "$OS_TYPE" = "ubuntu" ]; then
    USE_CLOUD_INIT="yes"
  else
    USE_CLOUD_INIT="${PVE_CLOUD_INIT:-no}"
  fi
  echo -e "${BOLD:-}${DGN:-}Cloud-Init: ${BGN:-}${USE_CLOUD_INIT}${CL:-}"
}

function get_image_url() {
  local arch=$(dpkg --print-architecture)
  case $OS_TYPE in
  debian)
    if [ "$USE_CLOUD_INIT" = "yes" ]; then
      echo "https://cloud.debian.org/images/cloud/${OS_CODENAME}/latest/debian-${OS_VERSION}-generic-${arch}.qcow2"
    else
      echo "https://cloud.debian.org/images/cloud/${OS_CODENAME}/latest/debian-${OS_VERSION}-nocloud-${arch}.qcow2"
    fi
    ;;
  ubuntu)
    echo "https://cloud-images.ubuntu.com/${OS_CODENAME}/current/${OS_CODENAME}-server-cloudimg-${arch}.img"
    ;;
  esac
}

# ==============================================================================
# SETTINGS (non-interactive — env vars or defaults)
# ==============================================================================
function apply_settings() {
  select_os
  select_cloud_init

  VMID="${PVE_VMID:-$(get_valid_nextid)}"
  FORMAT=""
  MACHINE=" -machine q35"
  DISK_CACHE=""
  DISK_SIZE="${PVE_DISK:-10G}"
  HN="${PVE_HOSTNAME:-docker}"
  CPU_TYPE=" -cpu host"
  CORE_COUNT="${PVE_CPU:-2}"
  RAM_SIZE="${PVE_RAM:-4096}"
  BRG="${PVE_BRIDGE:-vmbr0}"
  MAC="${PVE_MAC:-$GEN_MAC}"
  VLAN=""
  MTU=""
  START_VM="${PVE_START:-yes}"
  METHOD="default"

  [ -n "${PVE_VLAN:-}" ] && VLAN=",tag=$PVE_VLAN"
  [ -n "${PVE_MTU:-}" ] && MTU=",mtu=$PVE_MTU"

  echo -e "${BOLD:-}${DGN:-}Virtual Machine ID: ${BGN:-}${VMID}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Machine Type: ${BGN:-}Q35 (Modern)${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Disk Size: ${BGN:-}${DISK_SIZE}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Hostname: ${BGN:-}${HN}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}CPU Model: ${BGN:-}Host${CL:-}"
  echo -e "${BOLD:-}${DGN:-}CPU Cores: ${BGN:-}${CORE_COUNT}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}RAM Size: ${BGN:-}${RAM_SIZE}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Bridge: ${BGN:-}${BRG}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}MAC Address: ${BGN:-}${MAC}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Start VM when completed: ${BGN:-}${START_VM}${CL:-}"
  echo -e "${BOLD:-}${DGN:-}Creating a Docker VM using the above settings${CL:-}"
}

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
header_info

check_root
arch_check
pve_check

apply_settings
post_to_api_vm

# ==============================================================================
# STORAGE SELECTION (non-interactive — env var or auto-detect)
# ==============================================================================
msg_info "Validating Storage"

if [ -n "${PVE_STORAGE:-}" ]; then
  STORAGE="$PVE_STORAGE"
else
  STORAGE_MENU=()
  while read -r line; do
    TAG=$(echo $line | awk '{print $1}')
    STORAGE_MENU+=("$TAG")
  done < <(pvesm status -content images | awk 'NR>1')

  VALID=$(pvesm status -content images | awk 'NR>1')
  if [ -z "$VALID" ]; then
    msg_error "Unable to detect a valid storage location."
    exit 1
  fi
  STORAGE="${STORAGE_MENU[0]}"
fi

msg_ok "Using ${CL}${BL}$STORAGE${CL} ${GN}for Storage Location."
msg_ok "Virtual Machine ID is ${CL}${BL}$VMID${CL}."

# ==============================================================================
# PREREQUISITES
# ==============================================================================
if ! command -v virt-customize &>/dev/null; then
  msg_info "Installing libguestfs-tools"
  apt-get -qq update >/dev/null
  apt-get -qq install libguestfs-tools lsb-release -y >/dev/null
  apt-get -qq install dhcpcd-base -y >/dev/null 2>&1 || true
  msg_ok "Installed libguestfs-tools"
fi

# ==============================================================================
# IMAGE DOWNLOAD
# ==============================================================================
msg_info "Retrieving the URL for the ${OS_DISPLAY} Qcow2 Disk Image"
URL=$(get_image_url)
CACHE_DIR="/var/lib/vz/template/cache"
CACHE_FILE="$CACHE_DIR/$(basename "$URL")"
mkdir -p "$CACHE_DIR"
msg_ok "${CL}${BL}${URL}${CL}"

if [[ ! -s "$CACHE_FILE" ]]; then
  curl -f#SL -o "$CACHE_FILE" "$URL"
  echo -en "\e[1A\e[0K"
  msg_ok "Downloaded ${CL}${BL}$(basename "$CACHE_FILE")${CL}"
else
  msg_ok "Using cached image ${CL}${BL}$(basename "$CACHE_FILE")${CL}"
fi

# ==============================================================================
# STORAGE TYPE DETECTION
# ==============================================================================
STORAGE_TYPE=$(pvesm status -storage "$STORAGE" | awk 'NR>1 {print $2}')
case $STORAGE_TYPE in
nfs | dir)
  DISK_EXT=".qcow2"
  DISK_REF="$VMID/"
  DISK_IMPORT="--format qcow2"
  THIN=""
  ;;
btrfs)
  DISK_EXT=".raw"
  DISK_REF="$VMID/"
  DISK_IMPORT="--format raw"
  FORMAT=",efitype=4m"
  THIN=""
  ;;
*)
  DISK_EXT=""
  DISK_REF=""
  DISK_IMPORT="--format raw"
  ;;
esac

# ==============================================================================
# IMAGE CUSTOMIZATION WITH DOCKER
# ==============================================================================
msg_info "Preparing ${OS_DISPLAY} image with Docker"

WORK_FILE=$(mktemp --suffix=.qcow2)
cp "$CACHE_FILE" "$WORK_FILE"

export LIBGUESTFS_BACKEND_SETTINGS=dns=8.8.8.8,1.1.1.1

DOCKER_PREINSTALLED="no"

# Install qemu-guest-agent and Docker during image customization
msg_info "Installing base packages in image"
if virt-customize -a "$WORK_FILE" --install qemu-guest-agent,curl,ca-certificates >/dev/null 2>&1; then
  msg_ok "Installed base packages"

  msg_info "Installing Docker (this may take 2-5 minutes)"
  if virt-customize -q -a "$WORK_FILE" --run-command "curl -fsSL https://get.docker.com | sh" >/dev/null 2>&1 &&
    virt-customize -q -a "$WORK_FILE" --run-command "systemctl enable docker" >/dev/null 2>&1; then
    msg_ok "Installed Docker"

    msg_info "Configuring Docker daemon"
    virt-customize -q -a "$WORK_FILE" --run-command "mkdir -p /etc/docker" >/dev/null 2>&1
    virt-customize -q -a "$WORK_FILE" --run-command 'cat > /etc/docker/daemon.json << EOF
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF' >/dev/null 2>&1
    DOCKER_PREINSTALLED="yes"
    msg_ok "Configured Docker daemon"
  else
    msg_ok "Docker will be installed on first boot"
  fi
else
  msg_ok "Packages will be installed on first boot"
fi

msg_info "Finalizing image (hostname, SSH config)"
virt-customize -q -a "$WORK_FILE" --hostname "${HN}" >/dev/null 2>&1 || true
virt-customize -q -a "$WORK_FILE" --run-command "truncate -s 0 /etc/machine-id" >/dev/null 2>&1 || true
virt-customize -q -a "$WORK_FILE" --run-command "rm -f /var/lib/dbus/machine-id" >/dev/null 2>&1 || true

# Configure SSH
if [ "$USE_CLOUD_INIT" = "yes" ]; then
  virt-customize -q -a "$WORK_FILE" --run-command "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config" >/dev/null 2>&1 || true
  virt-customize -q -a "$WORK_FILE" --run-command "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config" >/dev/null 2>&1 || true
else
  # Auto-login for nocloud images
  virt-customize -q -a "$WORK_FILE" --run-command "mkdir -p /etc/systemd/system/serial-getty@ttyS0.service.d" >/dev/null 2>&1 || true
  virt-customize -q -a "$WORK_FILE" --run-command 'cat > /etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I \$TERM
EOF' >/dev/null 2>&1 || true
  virt-customize -q -a "$WORK_FILE" --run-command "mkdir -p /etc/systemd/system/getty@tty1.service.d" >/dev/null 2>&1 || true
  virt-customize -q -a "$WORK_FILE" --run-command 'cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I \$TERM
EOF' >/dev/null 2>&1 || true
fi

# Inject SSH key if provided
if [ -n "${PVE_SSH_KEY:-}" ]; then
  virt-customize -q -a "$WORK_FILE" --run-command "mkdir -p /root/.ssh && chmod 700 /root/.ssh" >/dev/null 2>&1 || true
  virt-customize -q -a "$WORK_FILE" --run-command "echo '${PVE_SSH_KEY}' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys" >/dev/null 2>&1 || true
  # Enable SSH for nocloud images
  virt-customize -q -a "$WORK_FILE" --run-command "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config" >/dev/null 2>&1 || true
  msg_ok "Injected SSH public key"
fi

msg_ok "Finalized image"

# First-boot Docker install fallback
if [ "$DOCKER_PREINSTALLED" = "no" ]; then
  if virt-customize -q -a "$WORK_FILE" --run-command 'cat > /root/install-docker.sh << "DOCKERSCRIPT"
#!/bin/bash
exec > /var/log/install-docker.log 2>&1
echo "[$(date)] Starting Docker installation"

for i in {1..30}; do
  ping -c 1 8.8.8.8 >/dev/null 2>&1 && break
  sleep 2
done

apt-get update
apt-get install -y qemu-guest-agent curl ca-certificates
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

mkdir -p /etc/docker
cat > /etc/docker/daemon.json << DAEMON
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
DAEMON
systemctl restart docker

touch /root/.docker-installed
echo "[$(date)] Docker installation completed"
DOCKERSCRIPT
chmod +x /root/install-docker.sh' >/dev/null 2>&1; then

    virt-customize -q -a "$WORK_FILE" --run-command 'cat > /etc/systemd/system/install-docker.service << "DOCKERSERVICE"
[Unit]
Description=Install Docker on First Boot
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/root/.docker-installed

[Service]
Type=oneshot
ExecStart=/root/install-docker.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
DOCKERSERVICE
systemctl enable install-docker.service' >/dev/null 2>&1 || true
  else
    echo "WARNING: virt-customize failed. Docker must be installed manually: curl -fsSL https://get.docker.com | sh" >&2
  fi
fi

# Resize disk
msg_info "Resizing disk image to ${DISK_SIZE}"
qemu-img resize "$WORK_FILE" "${DISK_SIZE}" >/dev/null 2>&1
msg_ok "Resized disk image"

# ==============================================================================
# VM CREATION
# ==============================================================================
msg_info "Creating Docker VM shell"

qm create $VMID -agent 1${MACHINE} -tablet 0 -localtime 1 -bios ovmf${CPU_TYPE} -cores $CORE_COUNT -memory $RAM_SIZE \
  -name $HN -tags community-script -net0 virtio,bridge=$BRG,macaddr=$MAC$VLAN$MTU -onboot 1 -ostype l26 -scsihw virtio-scsi-pci >/dev/null

msg_ok "Created VM shell"

# ==============================================================================
# DISK IMPORT
# ==============================================================================
msg_info "Importing disk into storage ($STORAGE)"

if qm disk import --help >/dev/null 2>&1; then
  IMPORT_CMD=(qm disk import)
else
  IMPORT_CMD=(qm importdisk)
fi

IMPORT_OUT="$("${IMPORT_CMD[@]}" "$VMID" "$WORK_FILE" "$STORAGE" ${DISK_IMPORT:-} 2>&1 || true)"
DISK_REF_IMPORTED="$(printf '%s\n' "$IMPORT_OUT" | sed -n "s/.*successfully imported disk '\([^']\+\)'.*/\1/p" | tr -d "\r\"'")"
[[ -z "$DISK_REF_IMPORTED" ]] && DISK_REF_IMPORTED="$(pvesm list "$STORAGE" | awk -v id="$VMID" '$5 ~ ("vm-"id"-disk-") {print $1":"$5}' | sort | tail -n1)"
[[ -z "$DISK_REF_IMPORTED" ]] && {
  msg_error "Unable to determine imported disk reference."
  echo "$IMPORT_OUT"
  exit 226
}

msg_ok "Imported disk (${CL}${BL}${DISK_REF_IMPORTED}${CL})"

rm -f "$WORK_FILE"

# ==============================================================================
# VM CONFIGURATION
# ==============================================================================
msg_info "Attaching EFI and root disk"

qm set "$VMID" \
  --efidisk0 "${STORAGE}:0,efitype=4m" \
  --scsi0 "${DISK_REF_IMPORTED},${DISK_CACHE}${THIN%,}" \
  --boot order=scsi0 \
  --serial0 socket >/dev/null

qm set $VMID --agent enabled=1 >/dev/null

msg_ok "Attached EFI and root disk"

set_description

# Cloud-Init configuration
if [ "$USE_CLOUD_INIT" = "yes" ]; then
  msg_info "Configuring Cloud-Init"
  setup_cloud_init "$VMID" "$STORAGE" "$HN" "yes"
  msg_ok "Cloud-Init configured"
fi

# Start VM
if [ "$START_VM" == "yes" ]; then
  msg_info "Starting Docker VM"
  qm start $VMID >/dev/null 2>&1
  msg_ok "Started Docker VM"
fi

# ==============================================================================
# FINAL OUTPUT
# ==============================================================================
VM_IP=""
if [ "$START_VM" == "yes" ]; then
  set +e
  for i in {1..10}; do
    VM_IP=$(qm guest cmd "$VMID" network-get-interfaces 2>/dev/null |
      jq -r '.[] | select(.name != "lo") | ."ip-addresses"[]? | select(."ip-address-type" == "ipv4") | ."ip-address"' 2>/dev/null |
      grep -v "^127\." | head -1) || true
    [ -n "$VM_IP" ] && break
    sleep 3
  done
  set -e
fi

echo -e "\n${INFO:-}${BOLD:-}${GN:-}Docker VM Configuration Summary:${CL:-}"
echo -e "  VM ID: ${VMID}"
echo -e "  Hostname: ${HN}"
echo -e "  OS: ${OS_DISPLAY}"
[ -n "$VM_IP" ] && echo -e "  IP Address: ${VM_IP}"

if [ "$DOCKER_PREINSTALLED" = "yes" ]; then
  echo -e "  Docker: Pre-installed (via get.docker.com)"
else
  echo -e "  Docker: Installing on first boot (wait 2-3 min)"
fi

if [ "$USE_CLOUD_INIT" = "yes" ]; then
  display_cloud_init_info "$VMID" "$HN" 2>/dev/null || true
fi

post_update_to_api "done" "none"
msg_ok "Completed successfully!\n"
