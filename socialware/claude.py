"""
Claude Agent SDK wrapper.

Generic L1 wrapper — no application-specific paths hardcoded.
"""

import os
from pathlib import Path
from typing import AsyncIterator, Any
from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions


async def query(
    prompt: str,
    cwd: str = None,
    plugin_dir: str | None = None,
) -> AsyncIterator[Any]:
    """
    Execute a Claude Agent query.

    Args:
        prompt: The query prompt
        cwd: Working directory, defaults to current directory
        plugin_dir: Path to plugin directory. If provided and exists,
                    loaded as a local plugin source.

    Yields:
        Raw message objects
    """
    if cwd is None:
        cwd = str(Path.cwd())

    plugins = None
    if plugin_dir:
        plugin_path = Path(plugin_dir)
        if plugin_path.exists():
            plugins = [{"type": "local", "path": str(plugin_path)}]

    env = {}
    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if http_proxy:
        env["http_proxy"] = http_proxy
    if https_proxy:
        env["https_proxy"] = https_proxy

    options = ClaudeAgentOptions(
        cwd=cwd,
        setting_sources=None,
        plugins=plugins,
        env=env,
    )

    async for message in sdk_query(prompt=prompt, options=options):
        yield message
