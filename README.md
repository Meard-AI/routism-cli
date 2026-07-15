# routism-cli

**Standalone** command-line / terminal UI operator for [Routism](https://github.com/Meard-AI/Routism).

This repo is **not** the Routism monorepo and **not** a desktop/Tauri app.  
It clones and drives the official product from GitHub so you can install, start, and operate the stack entirely from a terminal.

| | |
|--|--|
| Product (stack) | https://github.com/Meard-AI/Routism |
| This tool | CLI + TUI only |
| License | MIT |

## Prerequisites

- Python **3.10+**
- **git**
- **Docker** (API + web dashboard containers)
- **Ollama** on the host (orchestration models)

## Install this CLI

```bash
git clone https://github.com/Meard-AI/routism-cli.git
cd routism-cli
./install.sh          # puts `routism` on ~/.local/bin
# or:  pip install -e .
```

From a checkout without install:

```bash
./bin/routism --help
PYTHONPATH=. python3 -m routism_cli --help
```

## First-time product install + setup

```bash
routism install           # clones Meard-AI/Routism → ~/Routism (or $ROUTISM_HOME)
routism setup -y          # Ollama models + docker compose up
routism tui               # interactive terminal menu
```

Equivalent one-shot:

```bash
routism setup -y          # auto-clones product if missing
```

Default product path: `~/Routism`. Override:

```bash
export ROUTISM_HOME=/path/to/Routism
# or
routism install --dir /path/to/Routism
```

## Commands

| Command | Purpose |
|---------|---------|
| `routism install` | Clone official product repo if needed |
| `routism setup [-y]` | Full setup (product ensure + Docker + Ollama + models) |
| `routism tui` | Terminal menu UI (`--smoke`, `--once KEY`) |
| `routism doctor [--json]` | Health checks |
| `routism status [--json]` | Compose + endpoints |
| `routism start` / `stop` / `restart` | Stack lifecycle |
| `routism logs [-f] [api\|ui]` | Logs |
| `routism pull-engine [--json]` | Engine model pulls (NDJSON progress) |
| `routism open` | Open web dashboard in browser |
| `routism binaries` | PATH report for python3/docker/ollama |
| `routism env show` / `env set KEY=VALUE` | Allowlisted `.env` |
| `routism support` | Redacted support JSON |
| `routism agent-env` | Agent OpenAI base URL snippet |
| `routism probe [all\|api\|ui\|health]` | HTTP probes |
| `routism home` | Show resolved product root |
| `routism version` | CLI version |

## After stack is up

1. Open dashboard: `routism open` (http://localhost:3000)  
2. **Providers** → register workers (BYOK, max 5)  
3. **API keys** → create `rtm_…`  
4. Point agents at:

```bash
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="rtm_…"
# model: routism-ultra
```

## What this project is / is not

- **Is:** a thin operator for Docker Compose + host Ollama against the product clone  
- **Is not:** the Conductor/API source tree (that lives in Routism)  
- **Is not:** a macOS desktop / Tauri GUI  

## Development

```bash
cd routism-cli
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).
