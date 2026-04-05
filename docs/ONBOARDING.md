# AutoService — New Customer Setup Guide

How to fork AutoService and configure it for a new customer deployment.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Feishu app with bot capabilities (for IM channel)
- Claude API key

## Step 1: Fork the repo

```bash
gh repo fork h2oslabs/AutoService --clone --remote
cd AutoService
```

## Step 2: Create your plugin

```bash
mkdir -p plugins/your-customer
```

Create `plugins/your-customer/plugin.yaml`:

```yaml
name: your-customer
version: 0.1.0
description: Your Customer — AI customer service bot
mode: mock  # "mock" for development, "real" for production API calls
installer: fork

mcp_tools:
  - name: crm_lookup
    description: Look up customer record
    handler: tools.crm_lookup
    input_schema:
      type: object
      properties:
        query:
          type: string
          description: Customer name, email, or account ID
      required: [query]

http_routes:
  - path: /api/your-customer/lookup
    method: GET
    handler: routes.get_lookup

mock_server:
  seed_data: mock_data/customers.json
  database: .autoservice/database/your-customer/mock.db

references:
  - references/glossary.md
  - references/product-catalog.md
```

Implement the handlers:

- `plugins/your-customer/tools.py` — MCP tool functions (used by Feishu channel)
- `plugins/your-customer/routes.py` — HTTP route handlers (used by web server)

See `plugins/_example/` for a working reference.

## Step 3: Add reference materials

```bash
mkdir -p plugins/your-customer/references
```

Add files the AI agent should know about:

- `glossary.md` — Product terminology and abbreviations
- `product-catalog.md` — Product names, features, pricing
- `faq.md` — Common customer questions and answers

These are listed in `plugin.yaml` under `references:` and loaded into the agent's context.

## Step 4: Add customer-specific skills (optional)

If the generic skills (customer-service, knowledge-base, sales-demo, marketing) are not enough:

```bash
mkdir -p plugins/your-customer/skills/your-skill
```

Create a `SKILL.md` in that directory. Plugin skills are auto-discovered by `make setup` and symlinked into `skills/`.

## Step 5: Configure credentials

Copy the example `.env` and fill in your values:

```bash
cp .env.example .env
```

Required variables:
- `ANTHROPIC_API_KEY` — Claude API key
- `DEMO_ACCESS_CODE` — Access code for web chat (if using web channel)

For Feishu channel, create `.feishu-credentials.json`:

```json
{
  "app_id": "cli_xxxxx",
  "app_secret": "xxxxx"
}
```

## Step 6: Setup and run

```bash
make setup          # Symlinks, plugin discovery, runtime dirs
make run-channel    # Start Feishu IM channel
# or
make run-web        # Start web chat server
```

## Step 7: Import knowledge base data

If using the knowledge-base skill, import your product docs:

```bash
# Add documents to the KB
# (specific commands depend on your KB skill configuration)
```

## Step 8: Verify

```bash
make check          # Verify plugin discovery
```

Expected output:
```
==> Checking plugin discovery
  plugin skill: skills/your-skill
Found 1 plugin skill(s).
```

## Upstream merge workflow

To pull improvements from the upstream AutoService repo:

```bash
# One-time: add upstream remote
git remote add upstream https://github.com/h2oslabs/AutoService.git

# Periodic: merge upstream changes
git fetch upstream
git merge upstream/main

# Resolve conflicts in plugin-specific files (yours take priority)
# Core framework changes (autoservice/, feishu/, web/) should merge cleanly
```

Plugin files never conflict with upstream because each customer's `plugins/` directory is unique. Conflicts only arise if you modify framework code directly — prefer plugins and skills for customization.
