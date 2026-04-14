"""Backward-compatible shim — re-exports from socialware.claude + L2 pool_query."""

import logging
from pathlib import Path
from typing import AsyncIterator, Any

from socialware.claude import query as _upstream_query

log = logging.getLogger("autoservice.claude")

# L2 default plugin directory
_DEFAULT_PLUGIN_SUBDIR = ".autoservice/.claude"


def _resolve_plugin_dir(cwd: str | None = None) -> str:
    """Resolve the L2 plugin directory path."""
    return str((Path(cwd or Path.cwd()).absolute() / _DEFAULT_PLUGIN_SUBDIR))


async def query(prompt: str, cwd: str = None) -> AsyncIterator[Any]:
    """L2 query wrapper — injects autoservice plugin directory."""
    async for message in _upstream_query(
        prompt, cwd=cwd, plugin_dir=_resolve_plugin_dir(cwd),
    ):
        yield message


async def pool_query(prompt: str, cwd: str = None) -> AsyncIterator[Any]:
    """
    Use CC Pool for Claude Agent query (reuses pre-warmed subprocesses).

    Falls back to stateless query() when pool is unavailable.
    """
    from autoservice.cc_pool import get_pool, load_pool_config

    try:
        config = load_pool_config(cwd=cwd or str(Path.cwd()))
        pool = await get_pool(config)
        async for message in pool.query(prompt):
            yield message
    except Exception as e:
        log.warning("Pool query failed, falling back to stateless query: %s", e)
        async for message in query(prompt, cwd):
            yield message
