#!/usr/bin/env python3
"""
PVE Agent Scripts Converter

Converts community-scripts/ProxmoxVE interactive GUI scripts into
agent-friendly CLI scripts by:

1. Parsing all ct/*.sh scripts to extract app metadata -> catalog.json
2. Generating misc/agent-build.func (non-interactive build.func replacement)
3. Generating the pve-agent CLI wrapper
4. Updating README.md

Author: Imogen Labs
License: MIT
"""

import json
import os
import re
import sys
import stat
from pathlib import Path
from typing import Optional

# Resolve project root (parent of tools/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CT_DIR = PROJECT_ROOT / "ct"
MISC_DIR = PROJECT_ROOT / "misc"
INSTALL_DIR = PROJECT_ROOT / "install"


def parse_ct_script(filepath: Path) -> Optional[dict]:
    """Parse a ct/*.sh script and extract app metadata."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  WARN: could not read {filepath}: {e}", file=sys.stderr)
        return None

    lines = content.splitlines()

    entry = {
        "file": filepath.name,
        "app": None,
        "tags": [],
        "cpu": 1,
        "ram": 512,
        "disk": 2,
        "os": "debian",
        "version": "12",
        "unprivileged": True,
        "gpu": False,
        "source_url": None,
        "author": None,
        "has_update_script": False,
        "install_script": None,
    }

    for line in lines:
        stripped = line.strip()

        # Source URL from comment header
        m = re.match(r'^#\s*Source:\s*(https?://\S+)', stripped)
        if m:
            entry["source_url"] = m.group(1).rstrip("|").strip()

        # Author
        m = re.match(r'^#\s*Author:\s*(.+)', stripped)
        if m:
            entry["author"] = m.group(1).strip()

        # APP="Name"
        m = re.match(r'^APP="([^"]*)"', stripped)
        if m:
            entry["app"] = m.group(1)

        # var_tags
        m = re.match(r'^var_tags="\$\{var_tags:-([^}]*)}"', stripped)
        if m:
            entry["tags"] = [t.strip() for t in m.group(1).split(";") if t.strip()]

        # var_cpu
        m = re.match(r'^var_cpu="\$\{var_cpu:-(\d+)}"', stripped)
        if m:
            entry["cpu"] = int(m.group(1))

        # var_ram
        m = re.match(r'^var_ram="\$\{var_ram:-(\d+)}"', stripped)
        if m:
            entry["ram"] = int(m.group(1))

        # var_disk
        m = re.match(r'^var_disk="\$\{var_disk:-(\d+)}"', stripped)
        if m:
            entry["disk"] = int(m.group(1))

        # var_os
        m = re.match(r'^var_os="\$\{var_os:-([^}]*)}"', stripped)
        if m:
            entry["os"] = m.group(1)

        # var_version
        m = re.match(r'^var_version="\$\{var_version:-([^}]*)}"', stripped)
        if m:
            entry["version"] = m.group(1)

        # var_unprivileged
        m = re.match(r'^var_unprivileged="\$\{var_unprivileged:-(\d+)}"', stripped)
        if m:
            entry["unprivileged"] = m.group(1) == "1"

        # var_gpu
        m = re.match(r'^var_gpu="\$\{var_gpu:-([^}]*)}"', stripped)
        if m:
            entry["gpu"] = m.group(1).lower() == "yes"

        # update_script detection
        if re.match(r'^function\s+update_script\s*\(\)', stripped) or re.match(r'^update_script\s*\(\)', stripped):
            entry["has_update_script"] = True

    if not entry["app"]:
        return None

    # Derive install script path
    nsapp = entry["app"].lower().replace(" ", "").replace("-", "")
    # The actual convention uses the filename stem
    stem = filepath.stem  # e.g. "adguard" from "adguard.sh"
    install_path = INSTALL_DIR / f"{stem}-install.sh"
    if install_path.exists():
        entry["install_script"] = f"install/{stem}-install.sh"
    else:
        # Try nsapp variant
        install_path2 = INSTALL_DIR / f"{nsapp}-install.sh"
        if install_path2.exists():
            entry["install_script"] = f"install/{nsapp}-install.sh"

    return entry


def build_catalog():
    """Parse all ct/*.sh scripts and return the catalog."""
    catalog = []
    ct_files = sorted(CT_DIR.glob("*.sh"))

    print(f"Parsing {len(ct_files)} CT scripts...", file=sys.stderr)

    for ct_file in ct_files:
        entry = parse_ct_script(ct_file)
        if entry:
            catalog.append(entry)
        else:
            print(f"  SKIP: {ct_file.name} (no APP= found)", file=sys.stderr)

    print(f"Parsed {len(catalog)} apps successfully.", file=sys.stderr)
    return catalog


def write_catalog(catalog: list[dict]):
    """Write catalog.json to project root."""
    out = PROJECT_ROOT / "catalog.json"
    with open(out, "w") as f:
        json.dump({
            "version": "1.0.0",
            "generated_by": "tools/convert.py",
            "app_count": len(catalog),
            "apps": catalog,
        }, f, indent=2)
    print(f"Wrote {out} ({len(catalog)} apps)", file=sys.stderr)


def write_agent_build_func():
    """Generate misc/agent-build.func — non-interactive replacement for build.func."""
    out = MISC_DIR / "agent-build.func"
    content = r'''#!/usr/bin/env bash
# ==============================================================================
# AGENT-BUILD.FUNC — Non-Interactive LXC Container Build Functions
# ==============================================================================
#
# Drop-in replacement for build.func, designed for AI agents and automation.
# All whiptail/dialog calls removed. Settings accepted via environment variables.
#
# Environment Variables (override defaults from ct/*.sh):
#   PVE_CPU=N          — CPU cores
#   PVE_RAM=N          — RAM in MB
#   PVE_DISK=N         — Disk in GB
#   PVE_CTID=N         — Container ID (auto if unset)
#   PVE_HOSTNAME=NAME  — Container hostname
#   PVE_OS=NAME        — OS type (debian, ubuntu, alpine)
#   PVE_VERSION=VER    — OS version
#   PVE_BRIDGE=NAME    — Network bridge (default: vmbr0)
#   PVE_NET=CIDR       — Network config (default: dhcp)
#   PVE_GATEWAY=IP     — Gateway IP
#   PVE_VLAN=N         — VLAN tag
#   PVE_MTU=N          — MTU
#   PVE_MAC=ADDR       — MAC address
#   PVE_PASSWORD=PW    — Container root password
#   PVE_SSH=yes|no     — Enable SSH
#   PVE_SSH_KEY=KEY    — SSH authorized key
#   PVE_UNPRIVILEGED=0|1 — Container type
#   PVE_GPU=yes|no     — GPU passthrough
#   PVE_VERBOSE=yes|no — Verbose mode
#   PVE_TAGS=t1;t2     — Additional tags
#   PVE_STORAGE=NAME   — Container storage
#   PVE_TEMPLATE_STORAGE=NAME — Template storage
#   PVE_FUSE=yes|no    — Enable FUSE
#   PVE_TUN=yes|no     — Enable TUN
#
# Flags:
#   PVE_JSON=1         — JSON output mode (all messages as JSON to stdout)
#   PVE_DRY_RUN=1      — Show what would be done without executing
#   PVE_SILENT=1       — Suppress all non-error output
#
# Exit Codes:
#   0 = success
#   1 = error
#   2 = invalid arguments
#
# Generated by tools/convert.py — Imogen Labs
# ==============================================================================

# --- Output Helpers -----------------------------------------------------------

_agent_json() {
  local level="$1" msg="$2"
  printf '{"level":"%s","msg":"%s","ts":"%s"}\n' "$level" "$msg" "$(date -Iseconds)" >&2
}

_agent_log() {
  local level="$1" msg="$2"
  if [[ "${PVE_JSON:-0}" == "1" ]]; then
    _agent_json "$level" "$msg"
  elif [[ "${PVE_SILENT:-0}" != "1" ]]; then
    echo "[$level] $msg" >&2
  fi
}

msg_info()  { _agent_log "INFO"  "$*"; }
msg_ok()    { _agent_log "OK"    "$*"; }
msg_error() { _agent_log "ERROR" "$*"; }
msg_warn()  { _agent_log "WARN"  "$*"; }
msg_custom(){ _agent_log "INFO"  "$3"; }
msg_debug() { [[ "${PVE_VERBOSE:-no}" == "yes" ]] && _agent_log "DEBUG" "$*"; }

# No-op display functions (replace interactive UI)
header_info() { :; }
color() { :; }
echo_default() { :; }
exit_script() { exit 0; }
msg_menu() { :; }

# Color variables (set to empty — no ANSI in agent mode)
RD="" GN="" BL="" YW="" CL="" BOLD="" TAB="" CM="" CROSS=""
INFO="" DEFAULT="" ADVANCED="" CREATING="" GATEWAY="" NETWORK=""
BGN="" BFR="" HOLD="" SPINNER_PID=""

# Spinner no-ops
spinner() { :; }
start_spinner() { :; }
stop_spinner() { :; }

# STD mode: suppress or passthrough depending on verbose
set_std_mode() {
  if [[ "${PVE_VERBOSE:-no}" == "yes" ]] || [[ "${VERBOSE:-no}" == "yes" ]]; then
    STD=""
  else
    STD="silent"
  fi
}

silent() {
  "$@" >/dev/null 2>&1
}

# --- Variable Initialization --------------------------------------------------

variables() {
  NSAPP=$(echo "${APP,,}" | tr -d ' ')
  var_install="${NSAPP}-install"
  INTEGER='^[0-9]+([.][0-9]+)?$'
  PVEHOST_NAME=$(hostname)
  DIAGNOSTICS="no"
  METHOD="agent"
  RANDOM_UUID="$(cat /proc/sys/kernel/random/uuid)"
  EXECUTION_ID="${RANDOM_UUID}"
  SESSION_ID="${RANDOM_UUID:0:8}"
  BUILD_LOG="/tmp/create-lxc-${SESSION_ID}.log"
  CTTYPE="${CTTYPE:-${CT_TYPE:-1}}"

  if command -v pveversion >/dev/null 2>&1; then
    PVEVERSION="$(pveversion | awk -F'/' '{print $2}' | awk -F'-' '{print $1}')"
  else
    PVEVERSION="N/A"
  fi
  KERNEL_VERSION=$(uname -r)

  # Capture app-declared defaults
  [[ -n "${var_cpu:-}" && "${var_cpu}" =~ ^[0-9]+$ ]] && export APP_DEFAULT_CPU="${var_cpu}"
  [[ -n "${var_ram:-}" && "${var_ram}" =~ ^[0-9]+$ ]] && export APP_DEFAULT_RAM="${var_ram}"
  [[ -n "${var_disk:-}" && "${var_disk}" =~ ^[0-9]+$ ]] && export APP_DEFAULT_DISK="${var_disk}"

  # Apply PVE_* environment overrides
  [[ -n "${PVE_CPU:-}" ]]       && var_cpu="$PVE_CPU"
  [[ -n "${PVE_RAM:-}" ]]       && var_ram="$PVE_RAM"
  [[ -n "${PVE_DISK:-}" ]]      && var_disk="$PVE_DISK"
  [[ -n "${PVE_OS:-}" ]]        && var_os="$PVE_OS"
  [[ -n "${PVE_VERSION:-}" ]]   && var_version="$PVE_VERSION"
  [[ -n "${PVE_HOSTNAME:-}" ]]  && var_hostname="$PVE_HOSTNAME"
  [[ -n "${PVE_BRIDGE:-}" ]]    && var_brg="$PVE_BRIDGE"
  [[ -n "${PVE_NET:-}" ]]       && var_net="$PVE_NET"
  [[ -n "${PVE_GATEWAY:-}" ]]   && var_gateway="$PVE_GATEWAY"
  [[ -n "${PVE_VLAN:-}" ]]      && var_vlan="$PVE_VLAN"
  [[ -n "${PVE_MTU:-}" ]]       && var_mtu="$PVE_MTU"
  [[ -n "${PVE_MAC:-}" ]]       && var_mac="$PVE_MAC"
  [[ -n "${PVE_PASSWORD:-}" ]]  && var_pw="$PVE_PASSWORD"
  [[ -n "${PVE_SSH:-}" ]]       && var_ssh="$PVE_SSH"
  [[ -n "${PVE_SSH_KEY:-}" ]]   && var_ssh_authorized_key="$PVE_SSH_KEY"
  [[ -n "${PVE_UNPRIVILEGED:-}" ]] && var_unprivileged="$PVE_UNPRIVILEGED"
  [[ -n "${PVE_GPU:-}" ]]       && var_gpu="$PVE_GPU"
  [[ -n "${PVE_VERBOSE:-}" ]]   && var_verbose="$PVE_VERBOSE"
  [[ -n "${PVE_TAGS:-}" ]]      && var_tags="$PVE_TAGS"
  [[ -n "${PVE_STORAGE:-}" ]]   && var_container_storage="$PVE_STORAGE"
  [[ -n "${PVE_TEMPLATE_STORAGE:-}" ]] && var_template_storage="$PVE_TEMPLATE_STORAGE"
  [[ -n "${PVE_FUSE:-}" ]]      && var_fuse="$PVE_FUSE"
  [[ -n "${PVE_TUN:-}" ]]       && var_tun="$PVE_TUN"
  [[ -n "${PVE_CTID:-}" ]]      && var_ctid="$PVE_CTID"
}

# --- Core Functions (sourced from upstream, kept intact) ----------------------

# Source the real core/error functions from local repo
_AGENT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${_AGENT_SCRIPT_DIR}/api.func" ]]; then
  source "${_AGENT_SCRIPT_DIR}/api.func"
fi

if [[ -f "${_AGENT_SCRIPT_DIR}/core.func" ]]; then
  source "${_AGENT_SCRIPT_DIR}/core.func"
  if [[ -f "${_AGENT_SCRIPT_DIR}/error_handler.func" ]]; then
    source "${_AGENT_SCRIPT_DIR}/error_handler.func"
  fi
  if declare -f load_functions >/dev/null 2>&1; then
    load_functions
  fi
else
  # Fallback: source from upstream if local files not available
  if command -v curl >/dev/null 2>&1; then
    source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/core.func) 2>/dev/null || true
    source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/error_handler.func) 2>/dev/null || true
    if declare -f load_functions >/dev/null 2>&1; then
      load_functions
    fi
  fi
fi

catch_errors() {
  set -Eeuo pipefail
  trap 'error_handler $LINENO "$BASH_COMMAND"' ERR 2>/dev/null || true
}

# --- Validation Functions (from build.func, no whiptail) ----------------------

validate_container_id() {
  local ctid="$1"
  [[ "$ctid" =~ ^[0-9]+$ ]] || return 1
  if command -v pvesh >/dev/null 2>&1; then
    local cluster_ids
    cluster_ids=$(pvesh get /cluster/resources --type vm --output-format json 2>/dev/null | grep -oP '"vmid"\s*:\s*\K[0-9]+' || true)
    if echo "$cluster_ids" | grep -qw "$ctid"; then
      return 1
    fi
  fi
  [[ ! -f "/etc/pve/lxc/${ctid}.conf" ]] || return 1
  return 0
}

get_valid_container_id() {
  local start="${1:-100}"
  local max_attempts=100
  local id="$start"
  for ((i = 0; i < max_attempts; i++)); do
    if validate_container_id "$id"; then
      echo "$id"
      return 0
    fi
    id=$((id + 1))
  done
  msg_error "Could not find available container ID after $max_attempts attempts"
  return 1
}

validate_hostname() {
  local hn="$1"
  [[ -n "$hn" ]] || return 1
  [[ ${#hn} -le 253 ]] || return 1
  [[ "$hn" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || return 1
  return 0
}

# --- IP Utilities (from build.func, kept intact) ------------------------------

ip_to_int() {
  local a b c d
  IFS=. read -r a b c d <<< "$1"
  echo $(( (a << 24) + (b << 16) + (c << 8) + d ))
}

int_to_ip() {
  local ip=$1
  echo "$(( (ip >> 24) & 255 )).$(( (ip >> 16) & 255 )).$(( (ip >> 8) & 255 )).$(( ip & 255 ))"
}

is_ip_range() {
  [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+-[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]]
}

resolve_ip_from_range() {
  local range="$1"
  local start_cidr="${range%%-*}"
  local end_cidr="${range##*-}"
  local start_ip="${start_cidr%%/*}"
  local end_ip="${end_cidr%%/*}"
  local cidr="${start_cidr##*/}"

  local start_int=$(ip_to_int "$start_ip")
  local end_int=$(ip_to_int "$end_ip")

  for (( ip=start_int; ip<=end_int; ip++ )); do
    local check_ip=$(int_to_ip "$ip")
    if ! ping -c 1 -W 1 "$check_ip" &>/dev/null; then
      NET_RESOLVED="${check_ip}/${cidr}"
      return 0
    fi
  done
  return 1
}

# --- Base Settings (from build.func, non-interactive) -------------------------

base_settings() {
  CT_TYPE=${var_unprivileged:-"1"}

  local final_disk="${var_disk:-4}"
  local final_cpu="${var_cpu:-1}"
  local final_ram="${var_ram:-1024}"

  if [[ -n "${APP_DEFAULT_DISK:-}" && "${APP_DEFAULT_DISK}" =~ ^[0-9]+$ ]]; then
    [[ "${APP_DEFAULT_DISK}" -gt "${final_disk}" ]] && final_disk="${APP_DEFAULT_DISK}"
  fi
  if [[ -n "${APP_DEFAULT_CPU:-}" && "${APP_DEFAULT_CPU}" =~ ^[0-9]+$ ]]; then
    [[ "${APP_DEFAULT_CPU}" -gt "${final_cpu}" ]] && final_cpu="${APP_DEFAULT_CPU}"
  fi
  if [[ -n "${APP_DEFAULT_RAM:-}" && "${APP_DEFAULT_RAM}" =~ ^[0-9]+$ ]]; then
    [[ "${APP_DEFAULT_RAM}" -gt "${final_ram}" ]] && final_ram="${APP_DEFAULT_RAM}"
  fi

  DISK_SIZE="${final_disk}"
  CORE_COUNT="${final_cpu}"
  RAM_SIZE="${final_ram}"
  VERBOSE=${var_verbose:-"${1:-no}"}

  PW=""
  if [[ -n "${var_pw:-}" ]]; then
    local _pw_raw="${var_pw}"
    case "$_pw_raw" in --password\ *) _pw_raw="${_pw_raw#--password }" ;; -password\ *) _pw_raw="${_pw_raw#-password }" ;; esac
    while [[ "$_pw_raw" == -* ]]; do _pw_raw="${_pw_raw#-}"; done
    [[ -n "$_pw_raw" ]] && PW="--password $_pw_raw"
  fi

  # Container ID
  NEXTID=$(pvesh get /cluster/nextid 2>/dev/null || echo "100")
  local requested_id="${var_ctid:-$NEXTID}"
  if ! validate_container_id "$requested_id"; then
    if [[ -n "${var_ctid:-}" ]]; then
      msg_warn "Container ID $requested_id already in use, finding next available"
    fi
    requested_id=$(get_valid_container_id "$requested_id")
  fi
  CT_ID="$requested_id"

  # Hostname
  local requested_hostname="${var_hostname:-$NSAPP}"
  requested_hostname=$(echo "${requested_hostname,,}" | tr -d ' ')
  if ! validate_hostname "$requested_hostname"; then
    [[ -n "${var_hostname:-}" ]] && msg_warn "Invalid hostname '$requested_hostname', using default: $NSAPP"
    requested_hostname="$NSAPP"
  fi
  HN="$requested_hostname"

  BRG=${var_brg:-"vmbr0"}
  NET=${var_net:-"dhcp"}

  if is_ip_range "$NET"; then
    msg_info "Scanning IP range: $NET"
    if resolve_ip_from_range "$NET"; then
      NET="$NET_RESOLVED"
    else
      msg_warn "Could not find free IP in range. Falling back to DHCP."
      NET="dhcp"
    fi
  fi

  IPV6_METHOD=${var_ipv6_method:-"none"}
  IPV6_STATIC=${var_ipv6_static:-""}
  GATE=${var_gateway:-""}
  APT_CACHER=${var_apt_cacher:-""}
  APT_CACHER_IP=${var_apt_cacher_ip:-""}
  MTU=${var_mtu:-""}
  SD=${var_searchdomain:-""}
  NS=${var_ns:-""}
  MAC=${var_mac:-""}
  VLAN=${var_vlan:-""}
  SSH=${var_ssh:-"no"}
  SSH_AUTHORIZED_KEY=${var_ssh_authorized_key:-""}
  UDHCPC_FIX=${var_udhcpc_fix:-""}
  TAGS="community-script;agent-created;${var_tags:-}"
  ENABLE_FUSE=${var_fuse:-"no"}
  ENABLE_TUN=${var_tun:-"no"}
  ENABLE_GPU=${var_gpu:-"no"}
  ENABLE_NESTING=${var_nesting:-"1"}
  ENABLE_KEYCTL=${var_keyctl:-"0"}
  ENABLE_MKNOD=${var_mknod:-"0"}
  PROTECT_CT=${var_protection:-"no"}

  if command -v timedatectl >/dev/null 2>&1; then
    timezone=$(timedatectl show --value --property=Timezone 2>/dev/null || echo "UTC")
  elif [ -f /etc/timezone ]; then
    timezone=$(cat /etc/timezone)
  else
    timezone="UTC"
  fi
  [[ "${timezone:-}" == Etc/* ]] && timezone="host"
  CT_TIMEZONE=${var_timezone:-"$timezone"}

  [[ -z "${var_os:-}" ]] && var_os="debian"
  [[ -z "${var_version:-}" ]] && var_version="12"
}

# --- Advanced Settings (non-interactive: all from env vars) -------------------

advanced_settings() {
  # In agent mode, all settings come from environment variables.
  # This is a no-op — base_settings already applied PVE_* overrides.
  msg_info "Agent mode: skipping interactive advanced settings"
}

# --- Storage Selection (non-interactive) --------------------------------------

select_storage() {
  local class="$1"
  local tag="${2:-}"

  # If user specified storage via env, use it
  if [[ "$class" == "container" && -n "${var_container_storage:-}" ]]; then
    echo "${var_container_storage}"
    return 0
  fi
  if [[ "$class" == "template" && -n "${var_template_storage:-}" ]]; then
    echo "${var_template_storage}"
    return 0
  fi

  # Auto-select: find first available storage of the right type
  local storage_list
  if [[ "$class" == "container" ]]; then
    storage_list=$(pvesm status -content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' | head -1)
  elif [[ "$class" == "template" ]]; then
    storage_list=$(pvesm status -content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' | head -1)
  fi

  if [[ -n "$storage_list" ]]; then
    echo "$storage_list"
    return 0
  fi

  # Fallback
  echo "local-lvm"
  return 0
}

# --- Install Script (non-interactive: auto-select default) --------------------

install_script() {
  if ! command -v pveversion >/dev/null 2>&1; then
    msg_error "This script must run on a Proxmox VE host"
    exit 1
  fi

  # Basic checks
  [[ "$(id -u)" -eq 0 ]] || { msg_error "Must run as root"; exit 1; }
  [[ "$(uname -m)" == "x86_64" ]] || { msg_error "Requires x86_64 architecture"; exit 1; }

  NEXTID=$(pvesh get /cluster/nextid 2>/dev/null || echo "100")

  if command -v timedatectl >/dev/null 2>&1; then
    timezone=$(timedatectl show --value --property=Timezone 2>/dev/null || echo "UTC")
  elif [ -f /etc/timezone ]; then
    timezone=$(cat /etc/timezone)
  else
    timezone="UTC"
  fi
  [[ "${timezone:-}" == Etc/* ]] && timezone="host"

  # Agent mode: always use default install, no interactive menu
  METHOD="agent"
  VERBOSE="${PVE_VERBOSE:-no}"
  base_settings "$VERBOSE"
  set_std_mode

  msg_info "Creating ${APP} container (ID: ${CT_ID}, CPU: ${CORE_COUNT}, RAM: ${RAM_SIZE}MB, Disk: ${DISK_SIZE}GB)"
}

# --- Start (non-interactive update mode) --------------------------------------

start() {
  if command -v pveversion >/dev/null 2>&1; then
    install_script || return 0
    return 0
  else
    # Running inside container — execute update
    VERBOSE="${PVE_VERBOSE:-no}"
    set_std_mode
    if declare -f ensure_profile_loaded >/dev/null 2>&1; then
      ensure_profile_loaded
    fi
    if declare -f get_lxc_ip >/dev/null 2>&1; then
      get_lxc_ip
    fi
    update_script
    if declare -f update_motd_ip >/dev/null 2>&1; then
      update_motd_ip
    fi
    if declare -f cleanup_lxc >/dev/null 2>&1; then
      cleanup_lxc
    fi
  fi
}

# --- Build Container (from build.func, non-interactive) -----------------------

build_container() {
  if [[ "${PVE_DRY_RUN:-0}" == "1" ]]; then
    local dry_run_data
    dry_run_data=$(cat <<DRYEOF
{
  "action": "create_container",
  "dry_run": true,
  "app": "${APP}",
  "ctid": ${CT_ID},
  "hostname": "${HN}",
  "os": "${var_os}",
  "version": "${var_version}",
  "cpu": ${CORE_COUNT},
  "ram_mb": ${RAM_SIZE},
  "disk_gb": ${DISK_SIZE},
  "bridge": "${BRG:-vmbr0}",
  "net": "${NET:-dhcp}",
  "unprivileged": ${CT_TYPE:-1},
  "gpu": "${ENABLE_GPU:-no}",
  "ssh": "${SSH:-no}",
  "tags": "${TAGS}"
}
DRYEOF
    )
    if [[ "${PVE_JSON:-0}" == "1" ]]; then
      echo "$dry_run_data"
    else
      msg_info "DRY RUN — would create container with these settings:"
      echo "$dry_run_data" >&2
    fi
    return 0
  fi

  # --- Actual container creation (all Proxmox API calls preserved) ---

  NET_STRING="-net0 name=eth0,bridge=${BRG:-vmbr0}"

  [[ -n "${MAC:-}" ]] && case "$MAC" in ,hwaddr=*) NET_STRING+="$MAC" ;; *) NET_STRING+=",hwaddr=$MAC" ;; esac
  NET_STRING+=",ip=${NET:-dhcp}"
  [[ -n "${GATE:-}" ]] && case "$GATE" in ,gw=*) NET_STRING+="$GATE" ;; *) NET_STRING+=",gw=$GATE" ;; esac
  [[ -n "${VLAN:-}" ]] && case "$VLAN" in ,tag=*) NET_STRING+="$VLAN" ;; *) NET_STRING+=",tag=$VLAN" ;; esac
  [[ -n "${MTU:-}" ]] && case "$MTU" in ,mtu=*) NET_STRING+="$MTU" ;; *) NET_STRING+=",mtu=$MTU" ;; esac

  # IPv6
  case "${IPV6_METHOD:-none}" in
    auto) NET_STRING+=",ip6=auto" ;;
    dhcp) NET_STRING+=",ip6=dhcp" ;;
    static) NET_STRING+=",ip6=$IPV6_ADDR"; [[ -n "${IPV6_GATE:-}" ]] && NET_STRING+=",gw6=$IPV6_GATE" ;;
  esac

  # Features
  FEATURES=""
  [[ "${ENABLE_NESTING:-1}" == "1" ]] && FEATURES="nesting=1"
  if [[ "$CT_TYPE" == "1" ]]; then
    [[ -n "$FEATURES" ]] && FEATURES="$FEATURES,"
    FEATURES="${FEATURES}keyctl=1"
  fi
  [[ "${ENABLE_FUSE:-no}" == "yes" ]] && { [[ -n "$FEATURES" ]] && FEATURES="$FEATURES,"; FEATURES="${FEATURES}fuse=1"; }

  # Download install functions
  TEMP_DIR=$(mktemp -d)
  pushd "$TEMP_DIR" >/dev/null
  local _func_url
  if [[ "$var_os" == "alpine" ]]; then
    _func_url="https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/alpine-install.func"
  else
    _func_url="https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/install.func"
  fi
  export FUNCTIONS_FILE_PATH="$(curl -fsSL "$_func_url")"
  if [[ -z "$FUNCTIONS_FILE_PATH" || ${#FUNCTIONS_FILE_PATH} -lt 100 ]]; then
    msg_error "Failed to download install functions from: $_func_url"
    exit 1
  fi

  # Core exports
  export DIAGNOSTICS="${DIAGNOSTICS:-no}"
  export RANDOM_UUID EXECUTION_ID SESSION_ID
  export CACHER="$APT_CACHER"
  export CACHER_IP="$APT_CACHER_IP"
  export tz="${CT_TIMEZONE:-$timezone}"
  export APPLICATION="$APP"
  export app="$NSAPP"
  export PASSWORD="$PW"
  export VERBOSE
  export SSH_ROOT="${SSH}"
  export SSH_AUTHORIZED_KEY
  export CTID="$CT_ID"
  export CTTYPE="$CT_TYPE"
  export DISK_SIZE CORE_COUNT RAM_SIZE
  export BRG NET GATE MAC VLAN MTU SD NS
  export TAGS HN
  export ENABLE_FUSE ENABLE_TUN ENABLE_GPU ENABLE_NESTING
  export ENABLE_KEYCTL ENABLE_MKNOD PROTECT_CT

  msg_info "Selecting storage..."
  CONTAINER_STORAGE=$(select_storage "container")
  TEMPLATE_STORAGE=$(select_storage "template")
  msg_ok "Storage: container=$CONTAINER_STORAGE, template=$TEMPLATE_STORAGE"

  msg_info "Creating LXC container ${CT_ID} for ${APP}..."

  # Call the real create_lxc_container function if available
  if declare -f create_lxc_container >/dev/null 2>&1; then
    create_lxc_container
  else
    # Inline minimal creation
    PCT_OSTYPE="$var_os"
    PCT_OSVERSION="$var_version"

    TEMPLATE=$(pveam available -section system 2>/dev/null | awk -v os="$var_os" -v ver="$var_version" '$0 ~ os"-"ver {print $2}' | sort -Vr | head -1)
    if [[ -z "$TEMPLATE" ]]; then
      msg_error "No template found for ${var_os}-${var_version}"
      exit 1
    fi

    # Download template
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE" >/dev/null 2>&1 || true

    PCT_OPTIONS=(
      -hostname "$HN"
      -tags "${TAGS//;/,}"
      -onboot 1
      -cores "$CORE_COUNT"
      -memory "$RAM_SIZE"
      -rootfs "${CONTAINER_STORAGE}:${DISK_SIZE}"
      -ostype "$var_os"
      "$NET_STRING"
    )

    [[ -n "$FEATURES" ]] && PCT_OPTIONS+=(-features "$FEATURES")
    [[ "$CT_TYPE" == "1" ]] && PCT_OPTIONS+=(-unprivileged 1)
    [[ -n "$PW" ]] && PCT_OPTIONS+=($PW)

    if ! pct create "$CT_ID" "${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}" "${PCT_OPTIONS[@]}" >>"$BUILD_LOG" 2>&1; then
      msg_error "Failed to create container. See $BUILD_LOG"
      exit 1
    fi
    msg_ok "Container ${CT_ID} created"

    # Start container
    msg_info "Starting container..."
    pct start "$CT_ID" >>"$BUILD_LOG" 2>&1
    sleep 3
    msg_ok "Container started"

    # Run install script
    local install_file="${_AGENT_SCRIPT_DIR}/../install/${var_install}.sh"
    if [[ -f "$install_file" ]]; then
      msg_info "Running install script: ${var_install}.sh"
      pct push "$CT_ID" "$install_file" "/tmp/${var_install}.sh"
      pct exec "$CT_ID" -- bash -c "chmod +x /tmp/${var_install}.sh && /tmp/${var_install}.sh" >>"$BUILD_LOG" 2>&1
      msg_ok "Install script completed"
    fi
  fi

  popd >/dev/null
  rm -rf "$TEMP_DIR"
}

# --- Description (from build.func, kept intact) -------------------------------

description() {
  IP=$(pct exec "$CTID" ip a s dev eth0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 || echo "unknown")
  CTID="$CT_ID"

  DESCRIPTION="<div align='center'><h2>${APP} LXC</h2><p>Created by pve-agent (Agent Edition)</p></div>"
  pct set "$CTID" -description "$DESCRIPTION" 2>/dev/null || true

  if [[ "${PVE_JSON:-0}" == "1" ]]; then
    cat <<JSONEOF
{
  "status": "success",
  "app": "${APP}",
  "ctid": ${CT_ID},
  "ip": "${IP}",
  "hostname": "${HN}",
  "cpu": ${CORE_COUNT},
  "ram_mb": ${RAM_SIZE},
  "disk_gb": ${DISK_SIZE}
}
JSONEOF
  fi
}

# --- Diagnostic stubs (telemetry disabled in agent mode) ----------------------

diagnostics_check() { DIAGNOSTICS="no"; }
diagnostics_menu() { :; }
post_update_to_api() { :; }

# --- Storage helpers ----------------------------------------------------------

check_container_storage() {
  # Check disk usage inside container
  local usage
  usage=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
  if [[ -n "$usage" && "$usage" -gt 95 ]]; then
    msg_warn "Container storage is ${usage}% full"
  fi
}

check_container_resources() {
  :  # No interactive warning in agent mode
}

# --- SSH helpers (non-interactive) --------------------------------------------

install_ssh_keys_into_ct() {
  [[ "${SSH:-no}" != "yes" ]] && return 0
  : "${SSH_KEYS_FILE:=}"
  if [[ -z "$SSH_KEYS_FILE" || ! -s "$SSH_KEYS_FILE" ]] && [[ -n "${SSH_AUTHORIZED_KEY:-}" ]]; then
    SSH_KEYS_FILE="$(mktemp)"
    printf '%s\n' "$SSH_AUTHORIZED_KEY" >"$SSH_KEYS_FILE"
  fi
  if [[ -n "$SSH_KEYS_FILE" && -s "$SSH_KEYS_FILE" ]]; then
    msg_info "Installing SSH keys into CT ${CTID:-$CT_ID}"
    pct exec "${CTID:-$CT_ID}" -- sh -c 'mkdir -p /root/.ssh && chmod 700 /root/.ssh' || return 1
    pct push "${CTID:-$CT_ID}" "$SSH_KEYS_FILE" /root/.ssh/authorized_keys >/dev/null 2>&1 || return 1
    pct exec "${CTID:-$CT_ID}" -- sh -c 'chmod 600 /root/.ssh/authorized_keys' || true
    msg_ok "Installed SSH keys"
  fi
  return 0
}

# --- Source tools.func if available -------------------------------------------
if [[ -f "${_AGENT_SCRIPT_DIR}/tools.func" ]]; then
  source "${_AGENT_SCRIPT_DIR}/tools.func"
fi
'''
    out.write_text(content)
    os.chmod(out, 0o755)
    print(f"Wrote {out}", file=sys.stderr)


def write_pve_agent_cli():
    """Generate the pve-agent CLI wrapper."""
    out = PROJECT_ROOT / "pve-agent"
    content = r'''#!/usr/bin/env python3
"""
pve-agent — CLI for Proxmox VE Community Scripts (Agent Edition)

Commands:
    list                    List all available apps (JSON)
    info <app>              Show app details
    search <keyword>        Search apps by name, tag, or OS
    create <app> [opts]     Create an LXC container
    update <app> --ctid N   Run update script on a container
    catalog                 Show catalog stats

Designed for AI agents and automation. No interactive prompts.

Author: Imogen Labs
License: MIT
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_FILE = SCRIPT_DIR / "catalog.json"
CT_DIR = SCRIPT_DIR / "ct"
AGENT_BUILD_FUNC = SCRIPT_DIR / "misc" / "agent-build.func"


def load_catalog() -> dict:
    if not CATALOG_FILE.exists():
        print("ERROR: catalog.json not found. Run: python3 tools/convert.py", file=sys.stderr)
        sys.exit(1)
    with open(CATALOG_FILE) as f:
        return json.load(f)


def find_app(catalog, name):
    """Find an app by name (case-insensitive, partial match)."""
    name_lower = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    # Exact match first
    for app in catalog["apps"]:
        app_normalized = app["app"].lower().replace("-", "").replace("_", "").replace(" ", "")
        if app_normalized == name_lower:
            return app
    # File stem match
    for app in catalog["apps"]:
        stem = app["file"].replace(".sh", "").lower().replace("-", "").replace("_", "")
        if stem == name_lower:
            return app
    # Partial match
    for app in catalog["apps"]:
        if name_lower in app["app"].lower().replace(" ", ""):
            return app
    return None


def cmd_list(args, catalog):
    """List all available apps."""
    apps = catalog["apps"]

    if args.format == "json":
        output = [{
            "name": a["app"],
            "file": a["file"],
            "cpu": a["cpu"],
            "ram": a["ram"],
            "disk": a["disk"],
            "os": a["os"],
            "tags": a["tags"],
        } for a in apps]
        print(json.dumps(output, indent=2))
    else:
        print(f"{'Name':<30} {'CPU':>4} {'RAM':>6} {'Disk':>5} {'OS':<10} {'Tags'}")
        print("-" * 85)
        for a in apps:
            tags = ";".join(a["tags"]) if a["tags"] else ""
            print(f"{a['app']:<30} {a['cpu']:>4} {a['ram']:>5}M {a['disk']:>4}G {a['os']:<10} {tags}")
        print(f"\nTotal: {len(apps)} apps")


def cmd_info(args, catalog):
    """Show detailed info about an app."""
    app = find_app(catalog, args.app)
    if not app:
        print(f"ERROR: App '{args.app}' not found", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(app, indent=2))
    else:
        print(f"App:            {app['app']}")
        print(f"Script:         ct/{app['file']}")
        print(f"Install:        {app.get('install_script', 'N/A')}")
        print(f"CPU:            {app['cpu']} cores")
        print(f"RAM:            {app['ram']} MB")
        print(f"Disk:           {app['disk']} GB")
        print(f"OS:             {app['os']} {app['version']}")
        print(f"Unprivileged:   {'yes' if app['unprivileged'] else 'no'}")
        print(f"GPU:            {'yes' if app['gpu'] else 'no'}")
        print(f"Tags:           {';'.join(app['tags']) if app['tags'] else 'none'}")
        print(f"Source:         {app.get('source_url', 'N/A')}")
        print(f"Author:         {app.get('author', 'N/A')}")
        print(f"Has Update:     {'yes' if app['has_update_script'] else 'no'}")


def cmd_search(args, catalog):
    """Search apps by keyword."""
    query = args.keyword.lower()
    results = []

    for app in catalog["apps"]:
        searchable = " ".join([
            app["app"].lower(),
            " ".join(app["tags"]),
            app["os"],
            app.get("source_url") or "",
            app.get("author") or "",
        ])
        if query in searchable:
            results.append(app)

    if args.format == "json":
        print(json.dumps([{
            "name": a["app"],
            "file": a["file"],
            "tags": a["tags"],
            "os": a["os"],
        } for a in results], indent=2))
    else:
        if not results:
            print(f"No apps found matching '{args.keyword}'")
            return
        print(f"Found {len(results)} apps matching '{args.keyword}':\n")
        for a in results:
            tags = ";".join(a["tags"]) if a["tags"] else ""
            print(f"  {a['app']:<30} [{a['os']}] {tags}")


def cmd_create(args, catalog):
    """Create a container."""
    app = find_app(catalog, args.app)
    if not app:
        print(f"ERROR: App '{args.app}' not found", file=sys.stderr)
        sys.exit(1)

    ct_script = CT_DIR / app["file"]
    if not ct_script.exists():
        print(f"ERROR: Script not found: {ct_script}", file=sys.stderr)
        sys.exit(1)

    # Build environment with overrides
    env = os.environ.copy()
    if args.cpu:
        env["PVE_CPU"] = str(args.cpu)
    if args.ram:
        env["PVE_RAM"] = str(args.ram)
    if args.disk:
        env["PVE_DISK"] = str(args.disk)
    if args.id:
        env["PVE_CTID"] = str(args.id)
    if args.hostname:
        env["PVE_HOSTNAME"] = args.hostname
    if args.bridge:
        env["PVE_BRIDGE"] = args.bridge
    if args.net:
        env["PVE_NET"] = args.net
    if args.gateway:
        env["PVE_GATEWAY"] = args.gateway
    if args.password:
        env["PVE_PASSWORD"] = args.password
    if args.ssh_key:
        env["PVE_SSH"] = "yes"
        env["PVE_SSH_KEY"] = args.ssh_key
    if args.storage:
        env["PVE_STORAGE"] = args.storage
    if args.json:
        env["PVE_JSON"] = "1"
    if args.dry_run:
        env["PVE_DRY_RUN"] = "1"
    if args.verbose:
        env["PVE_VERBOSE"] = "yes"

    # Patch the script to use agent-build.func instead of upstream build.func
    # We use a bash wrapper that sources agent-build.func then runs the script body
    agent_func = str(AGENT_BUILD_FUNC)

    wrapper = (
        '#!/usr/bin/env bash\n'
        f'source "{agent_func}"\n'
        '# Now source the CT script, but skip its first line (the upstream source)\n'
        f'eval "$(tail -n +2 "{ct_script}")"\n'
    )

    print(f"{'DRY RUN: ' if args.dry_run else ''}Creating {app['app']} container...", file=sys.stderr)

    result = subprocess.run(
        ["bash", "-c", wrapper],
        env=env,
        capture_output=not args.verbose,
        text=True,
    )

    if result.returncode != 0:
        if not args.verbose and result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    if args.verbose and result.stdout:
        print(result.stdout)


def cmd_update(args, catalog):
    """Run update script on a container."""
    app = find_app(catalog, args.app)
    if not app:
        print(f"ERROR: App '{args.app}' not found", file=sys.stderr)
        sys.exit(1)

    if not app["has_update_script"]:
        print(f"ERROR: {app['app']} does not have an update script", file=sys.stderr)
        sys.exit(1)

    if not args.ctid:
        print("ERROR: --ctid is required for update", file=sys.stderr)
        sys.exit(2)

    ct_script = CT_DIR / app["file"]
    agent_func = str(AGENT_BUILD_FUNC)

    env = os.environ.copy()
    env["PVE_VERBOSE"] = "yes" if args.verbose else "no"
    if args.json:
        env["PVE_JSON"] = "1"

    # For updates, we run inside the container
    # Push the script and execute it
    wrapper = (
        '#!/usr/bin/env bash\n'
        f'source "{agent_func}"\n'
        f'eval "$(tail -n +2 "{ct_script}")"\n'
    )

    print(f"Updating {app['app']} on CT {args.ctid}...", file=sys.stderr)

    result = subprocess.run(
        ["pct", "exec", str(args.ctid), "--", "bash", "-c", wrapper],
        env=env,
        capture_output=not args.verbose,
        text=True,
    )

    if result.returncode != 0:
        if not args.verbose and result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)


def cmd_catalog_stats(args, catalog):
    """Show catalog statistics."""
    apps = catalog["apps"]
    os_counts = {}
    tag_counts = {}
    for a in apps:
        os_counts[a["os"]] = os_counts.get(a["os"], 0) + 1
        for t in a["tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    stats = {
        "total_apps": len(apps),
        "with_gpu": sum(1 for a in apps if a["gpu"]),
        "with_update": sum(1 for a in apps if a["has_update_script"]),
        "with_install_script": sum(1 for a in apps if a.get("install_script")),
        "os_distribution": dict(sorted(os_counts.items(), key=lambda x: -x[1])),
        "top_tags": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:20]),
    }

    if args.format == "json":
        print(json.dumps(stats, indent=2))
    else:
        print(f"Total apps:           {stats['total_apps']}")
        print(f"With GPU support:     {stats['with_gpu']}")
        print(f"With update script:   {stats['with_update']}")
        print(f"With install script:  {stats['with_install_script']}")
        print(f"\nOS Distribution:")
        for os_name, count in stats["os_distribution"].items():
            print(f"  {os_name:<15} {count}")
        print(f"\nTop Tags:")
        for tag, count in stats["top_tags"].items():
            print(f"  {tag:<20} {count}")


def main():
    parser = argparse.ArgumentParser(
        prog="pve-agent",
        description="Proxmox VE Community Scripts — Agent Edition CLI",
    )
    parser.add_argument("--format", choices=["json", "table"], default="table",
                        help="Output format (default: table)")
    parser.add_argument("--json", action="store_true", help="Shorthand for --format json")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List all available apps")
    p_list.set_defaults(func=cmd_list)

    # info
    p_info = subparsers.add_parser("info", help="Show app details")
    p_info.add_argument("app", help="App name")
    p_info.set_defaults(func=cmd_info)

    # search
    p_search = subparsers.add_parser("search", help="Search apps")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.set_defaults(func=cmd_search)

    # create
    p_create = subparsers.add_parser("create", help="Create LXC container")
    p_create.add_argument("app", help="App name")
    p_create.add_argument("--cpu", type=int, help="CPU cores")
    p_create.add_argument("--ram", type=int, help="RAM in MB")
    p_create.add_argument("--disk", type=int, help="Disk in GB")
    p_create.add_argument("--id", type=int, help="Container ID")
    p_create.add_argument("--hostname", help="Container hostname")
    p_create.add_argument("--bridge", help="Network bridge")
    p_create.add_argument("--net", help="Network config (CIDR or dhcp)")
    p_create.add_argument("--gateway", help="Gateway IP")
    p_create.add_argument("--password", help="Root password")
    p_create.add_argument("--ssh-key", help="SSH authorized key")
    p_create.add_argument("--storage", help="Container storage")
    p_create.add_argument("--dry-run", action="store_true", help="Show what would be done")
    p_create.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_create.set_defaults(func=cmd_create)

    # update
    p_update = subparsers.add_parser("update", help="Update app in container")
    p_update.add_argument("app", help="App name")
    p_update.add_argument("--ctid", type=int, required=True, help="Container ID")
    p_update.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p_update.set_defaults(func=cmd_update)

    # catalog
    p_catalog = subparsers.add_parser("catalog", help="Show catalog statistics")
    p_catalog.set_defaults(func=cmd_catalog_stats)

    args = parser.parse_args()

    # Handle --json shorthand
    if args.json:
        args.format = "json"

    catalog = load_catalog()
    args.func(args, catalog)


if __name__ == "__main__":
    main()
'''
    out.write_text(content)
    os.chmod(out, out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Wrote {out}", file=sys.stderr)


def write_readme():
    """Write README.md."""
    out = PROJECT_ROOT / "README.md"
    content = '''# PVE Agent Scripts — Agent Edition

Non-interactive, CLI-first fork of [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE) for AI agents and automation.

## What Is This?

The upstream ProxmoxVE community scripts use whiptail/dialog for interactive GUI menus. That makes them unusable by AI agents, CI/CD pipelines, or any automation tool. This fork strips all interactive prompts and replaces them with environment variables and CLI flags.

**What changed:**
- `misc/agent-build.func` replaces `build.func` — zero whiptail/dialog calls
- `pve-agent` CLI provides structured JSON output for agent consumption
- `catalog.json` is a machine-readable index of all 466+ apps
- All `install/*.sh` scripts remain **untouched** — the actual app logic works as-is

**What stayed the same:**
- All Proxmox API calls (`pct create`, `pct set`, etc.)
- All apt/package installation logic
- All install scripts (`install/*.sh`)
- Upstream compatibility — can merge changes from community-scripts

## Quick Start

```bash
# List all available apps
./pve-agent list

# Search for an app
./pve-agent search docker

# Get details about an app
./pve-agent info plex

# Create a container with defaults
./pve-agent create adguard

# Create with custom resources
./pve-agent create plex --cpu 4 --ram 4096 --disk 16 --hostname plex-server

# Dry run (shows what would happen)
./pve-agent create adguard --dry-run

# JSON output mode (for agents)
./pve-agent --json list
./pve-agent --json info adguard
./pve-agent --json create adguard --dry-run
```

## Environment Variables

Instead of interactive prompts, configure via environment:

| Variable | Description | Default |
|----------|-------------|---------|
| `PVE_CPU` | CPU cores | App default |
| `PVE_RAM` | RAM in MB | App default |
| `PVE_DISK` | Disk in GB | App default |
| `PVE_CTID` | Container ID | Auto (next available) |
| `PVE_HOSTNAME` | Container hostname | App name |
| `PVE_OS` | OS type | App default |
| `PVE_VERSION` | OS version | App default |
| `PVE_BRIDGE` | Network bridge | vmbr0 |
| `PVE_NET` | Network config | dhcp |
| `PVE_GATEWAY` | Gateway IP | - |
| `PVE_VLAN` | VLAN tag | - |
| `PVE_MTU` | MTU | - |
| `PVE_MAC` | MAC address | - |
| `PVE_PASSWORD` | Root password | - |
| `PVE_SSH` | Enable SSH (yes/no) | no |
| `PVE_SSH_KEY` | SSH authorized key | - |
| `PVE_GPU` | GPU passthrough (yes/no) | no |
| `PVE_STORAGE` | Container storage | Auto-detected |
| `PVE_TEMPLATE_STORAGE` | Template storage | Auto-detected |
| `PVE_JSON` | JSON output mode (1) | 0 |
| `PVE_DRY_RUN` | Dry run mode (1) | 0 |
| `PVE_VERBOSE` | Verbose output (yes) | no |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| 2 | Invalid arguments |

## Architecture

```
pve-agent (Python CLI)
    |
    v
catalog.json  <--  tools/convert.py parses ct/*.sh
    |
    v
ct/*.sh  -->  source misc/agent-build.func (non-interactive)
    |
    v
install/*.sh  (untouched upstream install scripts)
```

## Regenerating the Catalog

```bash
python3 tools/convert.py
```

This parses all `ct/*.sh` scripts and regenerates:
- `catalog.json` — machine-readable app index
- `misc/agent-build.func` — non-interactive build functions
- `pve-agent` — CLI wrapper

## Credits

- **[tteck](https://github.com/tteck)** (RIP) — Original creator of Proxmox VE Helper Scripts
- **[community-scripts](https://github.com/community-scripts/ProxmoxVE)** — Community maintainers
- **Imogen Labs** — Agent Edition fork maintainer

## License

MIT — Same as upstream.
'''
    out.write_text(content)
    print(f"Wrote {out}", file=sys.stderr)


def main():
    print("=== PVE Agent Scripts Converter ===\n", file=sys.stderr)

    # 1. Parse catalog
    catalog = build_catalog()
    write_catalog(catalog)

    # 2. Generate agent-build.func
    write_agent_build_func()

    # 3. Generate pve-agent CLI
    write_pve_agent_cli()

    # 4. Update README
    write_readme()

    print(f"\nDone. Generated:", file=sys.stderr)
    print(f"  catalog.json          ({len(catalog)} apps)", file=sys.stderr)
    print(f"  misc/agent-build.func (non-interactive build functions)", file=sys.stderr)
    print(f"  pve-agent             (CLI wrapper)", file=sys.stderr)
    print(f"  README.md             (updated)", file=sys.stderr)


if __name__ == "__main__":
    main()
