#!/bin/bash
# autoservice.local.sh — local overrides (proxy, API keys, etc.)
# Sourced by autoservice.sh on startup. Tracked in git.

# ── Proxy ─────────────────────────────────────────────────────────────────
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
export no_proxy=localhost,127.0.0.1,::1
export NO_PROXY=$no_proxy
