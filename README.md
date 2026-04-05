# AutoService

Fork-based framework for building AI customer service and sales bots. Each customer deployment is a fork of this repo. Customer-specific behavior is defined through declarative plugins (`plugins/*/plugin.yaml`) — no framework code changes needed. Supports two channels: Feishu IM (MCP-based) and web chat (FastAPI).

## Quick start

```bash
make setup              # Symlinks, plugin discovery, runtime dirs
cp .env.example .env    # Configure API keys
make run-channel        # Start Feishu IM channel
# or
make run-web            # Start web chat server
```

## Documentation

- [CLAUDE.md](CLAUDE.md) — Development reference (commands, directory structure, plugin system)
- [docs/ONBOARDING.md](docs/ONBOARDING.md) — New customer setup guide (fork, plugin, configure, deploy)
- [docs/API_ARCHITECTURE.md](docs/API_ARCHITECTURE.md) — Plugin API design (plugin.yaml, handler resolution, mock/real modes)
- [docs/plans/](docs/plans/) — Architecture decisions and implementation plans
- [docs/changelog/CHANGELOG.md](docs/changelog/CHANGELOG.md) — Version history
