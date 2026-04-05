"""
Example plugin tools — MCP tool handlers.

Each function receives keyword arguments matching the input_schema
defined in plugin.yaml and returns a dict that becomes the tool result.
"""

# In-memory example records (a real plugin would query MockDB or an API)
_RECORDS = {
    "EX-001": {"id": "EX-001", "name": "Acme Corp", "status": "active"},
    "EX-002": {"id": "EX-002", "name": "Globex Inc", "status": "pending"},
}


async def echo(message: str) -> dict:
    """Echo back the input message — simplest possible tool handler."""
    return {"echo": message}


async def lookup(id: str) -> dict:
    """Look up a record by ID from the example database."""
    record = _RECORDS.get(id)
    if record is None:
        return {"error": f"Record '{id}' not found"}
    return {"record": record}
