# PVE Agent Scripts — Agent Edition

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
- Upstream compatibility — can merge changes from community-scripts**Compatibility:**- 465 CT scripts — all use the same source pattern, all work with pve-agent- 391/455 install scripts fully non-interactive — work perfectly- 57 install scripts have YES/NO prompts — auto-declined (defaults to No)- 35 install scripts have version/config prompts — use defaults when available- Tested: Docker, AdGuard Home, Nginx Proxy Manager — all FULL SUCCESS on Proxmox 8

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
- **[Imogen Labs](https://agents.imogenlabs.ai)** — Agent Edition fork maintainer

## Related

- **[OpenClaw Agent Templates](https://agents.imogenlabs.ai/#templates)** — Pre-built AI agent configs ($19-49) for monitoring, crypto, news, security, and more
- **[The Imogen Playbook](https://agents.imogenlabs.ai/#templates)** — How to build an AI operator from scratch ($149)
- **[Managed OpenClaw Hosting](https://agents.imogenlabs.ai/#pricing)** — Dedicated AI agent hosting ($29-89/mo)
- **[@imogenlabs/operator-kit](https://www.npmjs.com/package/@imogenlabs/operator-kit)** — Free OpenClaw operator scaffold (npm)

## License

MIT — Same as upstream.
