"""
Example plugin HTTP routes — FastAPI route handlers.

These are mounted by the web server under the prefix declared in
plugin.yaml http_routes.  Each handler calls the corresponding
function in tools.py so business logic stays in one place.

Note: plugin modules are loaded by plugin_loader via importlib (not
as real packages), so use sys.modules to reference sibling modules.
"""

import sys


def _get_tools():
    """Lazy-import the tools module registered by plugin_loader."""
    return sys.modules["autoservice.plugins._example.tools"]


async def post_echo(message: str) -> dict:
    """POST /api/example/echo — echo a message back."""
    tools = _get_tools()
    return await tools.echo(message=message)


async def get_record(record_id: str) -> dict:
    """GET /api/example/{record_id} — look up a record."""
    tools = _get_tools()
    return await tools.lookup(id=record_id)
