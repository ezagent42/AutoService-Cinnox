# AutoService — Plugin API Architecture

## Plugin mechanism

Plugins are the primary extension point. Each plugin lives in `plugins/<name>/` and is defined by a single `plugin.yaml` file. The plugin loader (`autoservice/plugin_loader.py`) scans `plugins/*/plugin.yaml` at startup, resolves all handler references to Python callables, and returns `Plugin` objects ready for registration.

No base class to inherit. No registry to call. Just YAML + Python functions.

## Dual interface

Every plugin can expose functionality through two interfaces:

| Interface | Used by | Declaration | Handler signature |
|-----------|---------|-------------|-------------------|
| **MCP tools** | Feishu IM channel | `mcp_tools:` in plugin.yaml | `def func(args: dict) -> str` |
| **HTTP routes** | Web chat server | `http_routes:` in plugin.yaml | FastAPI-compatible async handler |

Both interfaces call into the same plugin code. A plugin can declare tools only, routes only, or both.

## plugin.yaml structure

```yaml
name: my-plugin
version: 0.1.0
description: What this plugin does
mode: mock          # "mock" = use MockDB, "real" = call live APIs
installer: fork     # "fork" = customer-created, "upstream" = ships with AutoService

mcp_tools:
  - name: tool_name
    description: What the tool does (shown to AI agent)
    handler: tools.function_name     # module.function in plugin dir
    input_schema:                    # JSON Schema for tool arguments
      type: object
      properties:
        query:
          type: string
      required: [query]

http_routes:
  - path: /api/my-plugin/endpoint
    method: POST
    handler: routes.handler_name

mock_server:
  seed_data: mock_data/seed.json     # Initial data for MockDB
  database: .autoservice/database/my-plugin/mock.db

references:
  - references/glossary.md           # Files loaded into agent context
```

## Handler resolution

Handler references use `module.function` format. The loader:

1. Splits `tools.crm_lookup` into module=`tools`, function=`crm_lookup`
2. Looks for `plugins/<name>/tools.py`
3. Imports it as `autoservice.plugins.<name>.tools` (namespaced to avoid collisions)
4. Gets the `crm_lookup` attribute and verifies it's callable

This means handler modules are standard Python files — no decorators, no registration, just functions.

## Mock vs Real modes

- **mode: mock** — Plugin gets a `MockDB` instance (SQLite-backed) seeded from `mock_server.seed_data`. Good for demos and development without live API credentials.
- **mode: real** — No MockDB. Handlers are expected to call real APIs. The plugin manages its own API clients.

The mode is set in `plugin.yaml` and can be toggled per-deployment. Handler code can check the mode if it needs to branch behavior.

## Plugin loading flow

```
startup
  → plugin_loader.discover("plugins/")
    → scan plugins/*/plugin.yaml
    → for each plugin.yaml:
        → parse YAML
        → resolve mcp_tools[].handler → Python callables
        → resolve http_routes[].handler → Python callables
        → resolve references[] → file paths
        → init MockDB if mode=mock
        → return Plugin(tools=[], routes=[], ...)
  → register tools with MCP server (Feishu channel)
  → mount routes on FastAPI app (web server)
```

## Skill and plugin collaboration

Skills and plugins serve different roles:

| | Skills | Plugins |
|---|---|---|
| **What** | Claude Code skill (SKILL.md prompt) | Data + API integration |
| **Where** | `skills/<name>/SKILL.md` | `plugins/<name>/plugin.yaml` |
| **Who writes** | Framework author or customer | Framework author or customer |
| **Does what** | Guides agent behavior (prompts, instructions) | Provides tools the agent can call |

A typical customer deployment pairs a generic skill (e.g., `customer-service`) with a customer-specific plugin (e.g., `plugins/acme/`) that provides the actual CRM lookup, order tracking, and other tools the skill's instructions reference.

Skills tell the agent *how* to behave. Plugins give it *what* to work with.
