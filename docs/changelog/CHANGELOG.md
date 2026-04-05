# AutoService Changelog

## v0.1.0 (2026-04-05)

Initial release — extracted from autoservices v0.7.4.

### New
- Fork-based multi-customer architecture (one repo per customer)
- Declarative plugin system (plugins/*/plugin.yaml auto-discovery)
- Feishu MCP channel with plugin tool hosting
- Web chat server with access code authentication
- 4 generic skills: customer-service, knowledge-base, sales-demo, marketing
- Example plugin template (plugins/_example/)

### Migrated from autoservices
- Core package: 12 modules from skills/_shared/
- Web server: decomposed from 2174-line monolith into 7 modules
- Skills: genericized (removed Cinnox-specific content)
- Feishu channel: adapted from SaneLedger

### Architecture
- Based on autoservices v0.7.4 (Cinnox demo, 8 UAT rounds)
- Feishu channel pattern from SaneLedger
