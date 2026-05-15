# PVE Agent Scripts — Agent Edition

Non-interactive, CLI-first fork of [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE) for AI agents and automation.

## What Is This?

The upstream ProxmoxVE community scripts use whiptail/dialog for interactive GUI menus. That makes them unusable by AI agents, CI/CD pipelines, or any automation tool. This fork strips all interactive prompts and replaces them with environment variables and CLI flags.

**What changed:**
- `misc/agent-build.func` replaces `build.func` — zero whiptail/dialog calls
- `pve-agent` CLI provides structured JSON output for agent consumption
- `catalog.json` is a machine-readable index of all 509 apps
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

# JSON output mode (for agents) — works before or after subcommand
./pve-agent --json list
./pve-agent list --json
./pve-agent info adguard --json
./pve-agent create adguard --dry-run --json
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
| `PVE_PASSWORD` | Root password (auto-generates random 16-char if not set) | Auto |
| `PVE_SSH` | Enable SSH (yes/no) | no |
| `PVE_SSH_KEY` | SSH authorized key | - |
| `PVE_GPU` | GPU passthrough (yes/no) | no |
| `PVE_TUN` | TUN device passthrough (yes/no) | no |
| `PVE_FUSE` | FUSE support (yes/no) | no |
| `PVE_UNPRIVILEGED` | Container type (0=privileged, 1=unprivileged) | App default |
| `PVE_TAGS` | Additional tags (semicolon-separated) | - |
| `PVE_IPV6` | IPv6 method (none/auto/dhcp/static) | none |
| `PVE_IPV6_ADDR` | IPv6 address (CIDR, for static) | - |
| `PVE_IPV6_GW` | IPv6 gateway (for static) | - |
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

**Warning:** `convert.py` overwrites `pve-agent` and `misc/agent-build.func` on every run. Edit `tools/convert.py` if you need to change them — direct edits will be lost on next regeneration.

## Credits

- **[tteck](https://github.com/tteck)** (RIP) — Original creator of Proxmox VE Helper Scripts
- **[community-scripts](https://github.com/community-scripts/ProxmoxVE)** — Community maintainers
- **[Eight.ly](https://eight.ly)** — Agent Edition fork maintainer

## License

MIT — Same as upstream.
