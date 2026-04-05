# References

This directory holds reference materials that the AI agent can consult during conversations. Files listed in `plugin.yaml` under `references:` are loaded and made available to the agent.

Typical contents:

- **Glossaries** — domain-specific terms and definitions
- **Product documentation** — feature descriptions, specs, changelogs
- **Pricing tables** — plans, tiers, discounts, add-ons
- **FAQ sheets** — common questions and approved answers
- **Policy documents** — return policies, SLAs, escalation procedures

## Format

Any text-based format works (Markdown, plain text, CSV). Keep files focused — one topic per file — so the agent retrieves only what it needs.
