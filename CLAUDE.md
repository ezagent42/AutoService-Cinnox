# AutoService — Fork-Based Customer Service / Sales Bot Framework

## Overview

AutoService is a fork-based framework for building customer service and sales bots. Each customer deployment is a fork of this repo with customer-specific configuration via declarative plugins.

Two channels:
- **Feishu IM** (primary) — MCP-based, runs as `feishu/channel.py`
- **Web chat** (secondary) — FastAPI app at `web/app:app`

## Commands

- `make setup` — Create symlinks (.claude/ dirs, plugin skills), init runtime dirs
- `make run-channel` — Start Feishu IM channel (MCP server)
- `make run-web` — Start web chat (FastAPI, default port 8000)
- `make check` — Verify plugin discovery

## Directory Structure

```
feishu/              # Feishu IM channel (MCP server)
web/                 # Web chat channel (FastAPI)
autoservice/         # Core library (shared logic)
skills/              # Claude Code skills (symlinked into .claude/skills)
plugins/             # Customer-specific plugins (declarative)
commands/            # Claude Code commands (symlinked into .claude/commands)
agents/              # Claude Code agents (symlinked into .claude/agents)
hooks/               # Claude Code hooks (symlinked into .claude/hooks)
.autoservice/        # Runtime data — logs, cache, db (gitignored)
docs/                # Design docs and plans
```

## Plugin System

Each plugin lives in `plugins/<name>/` with `plugin.yaml` declaring MCP tools + HTTP routes.
Plugin tools are auto-loaded by `feishu/channel.py` (MCP) and `web/app.py` (HTTP).
Plugin skills in `plugins/<name>/skills/` are symlinked by `make setup`.

Run `make check` to verify plugin discovery.

## Fork Workflow

This repo is a **fork** of [AutoService upstream](https://github.com/ezagent42/AutoService).

### Upstream vs Fork responsibilities

| Upstream (AutoService) | Fork (this repo) |
|------------------------|-------------------|
| Core framework (`autoservice/`, `feishu/`, `web/`) | Customer plugins (`plugins/cinnox/`) |
| Generic skills (`skills/customer-service/`, `sales-demo/`, etc.) | Customer-specific skills (`skills/cinnox-demo/`) |
| Plugin loader, channel server, web server | Customer data (`.autoservice/`, credentials) |
| Documentation templates | Customer history (`docs/history/`) |

### Contributing improvements back to upstream

If you make improvements that are **not customer-specific** — bug fixes, framework enhancements, generic skill improvements — these should be contributed back to upstream:

```bash
# Ensure upstream remote is configured
git remote add upstream git@github.com:ezagent42/AutoService.git

# Create a branch for the improvement
git checkout -b fix/improve-plugin-loader

# Make your changes, commit, push to YOUR fork
git push origin fix/improve-plugin-loader

# Create PR targeting upstream/main (not your fork's main)
gh pr create --repo ezagent42/AutoService --base main --head allenwoods:fix/improve-plugin-loader
```

**Rule of thumb:** If the change would benefit other customers, PR it to upstream. If it's only relevant to this customer (Cinnox-specific terms, APIs, branding), keep it in the fork.

### Syncing with upstream

```bash
git fetch upstream
git merge upstream/main
# Resolve any conflicts (typically only in .autoservice-info.yaml)
```

## Credentials

- `.feishu-credentials.json` — Feishu app credentials (gitignored)
- `.autoservice/config.local.yaml` — Local API keys and endpoints (gitignored)
- `.env` — Environment variables (gitignored)
