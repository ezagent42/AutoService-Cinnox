"""
Channel MCP tools — reply, react, and plugin tools.

Extracted from channel.py for reuse in both:
- channel.py (legacy MCP stdio mode)
- channel_server.py pool mode (SDK MCP injection)

Usage:
    from channels.feishu.channel_tools import create_channel_mcp_server

    # For pool mode (in-process MCP server):
    server = create_channel_mcp_server(
        reply_callback=my_reply_fn,
        react_callback=my_react_fn,
        plugin_tools=plugins,
        instructions="...",
    )
    # Pass as McpSdkServerConfig: {"type": "sdk", "name": "channel", "instance": server}
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from mcp.server.lowlevel import Server
from mcp.types import Tool, TextContent

log = logging.getLogger("channel-tools")

# Type aliases for callbacks
ReplyCallback = Callable[[str, str], Awaitable[None]]   # (chat_id, text) -> None
ReactCallback = Callable[[str, str], Awaitable[None]]   # (message_id, emoji_type) -> None


# -- Tool definitions --------------------------------------------------------

REPLY_TOOL = Tool(
    name="reply",
    description=(
        "Send a message to a Feishu chat. The user reads Feishu, not this "
        "session -- anything you want them to see must go through this tool. "
        "chat_id is from the inbound <channel> tag (oc_xxx format)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "chat_id": {"type": "string", "description": "Feishu chat ID (oc_xxx)"},
            "text": {"type": "string", "description": "Message text"},
        },
        "required": ["chat_id", "text"],
    },
)

REACT_TOOL = Tool(
    name="react",
    description="Add an emoji reaction to a Feishu message",
    inputSchema={
        "type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Message ID (om_xxx)"},
            "emoji_type": {"type": "string", "description": "Feishu emoji (THUMBSUP, DONE, OK)"},
        },
        "required": ["message_id", "emoji_type"],
    },
)


# -- MCP Server factory ------------------------------------------------------

def create_channel_mcp_server(
    reply_callback: ReplyCallback,
    react_callback: ReactCallback | None = None,
    plugin_tools: list | None = None,
    instructions: str = "",
) -> Server:
    """Create an MCP Server with channel tools.

    Args:
        reply_callback: async fn(chat_id, text) — called when Claude invokes 'reply'
        react_callback: async fn(message_id, emoji_type) — called for 'react'
        plugin_tools: list of plugin tool objects with .name, .description, .input_schema, .handler
        instructions: system instructions text

    Returns:
        mcp.server.lowlevel.Server instance, ready for SDK injection.
    """
    plugin_tools = plugin_tools or []
    server = Server("autoservice-channel", instructions=instructions)

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        core = [REPLY_TOOL, REACT_TOOL]
        dynamic = [
            Tool(name=pt.name, description=pt.description, inputSchema=pt.input_schema)
            for pt in plugin_tools
        ]
        return core + dynamic

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "reply":
            chat_id = arguments["chat_id"]
            text = arguments["text"]
            await reply_callback(chat_id, text)
            log.info("Reply to %s: %s", chat_id, text[:60])
            return [TextContent(type="text", text=f"Sent to {chat_id}")]

        if name == "react":
            if react_callback:
                await react_callback(arguments["message_id"], arguments["emoji_type"])
                return [TextContent(type="text", text=f"Reacted {arguments['emoji_type']}")]
            return [TextContent(type="text", text="React not available")]

        for pt in plugin_tools:
            if pt.name == name:
                result = pt.handler(**arguments)
                if asyncio.iscoroutine(result):
                    result = await result
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        raise ValueError(f"Unknown tool: {name}")

    return server
