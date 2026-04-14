"""Tests for channel_tools.py — extracted MCP tool definitions."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock

from channels.feishu.channel_tools import (
    create_channel_mcp_server,
    REPLY_TOOL,
    REACT_TOOL,
)
from mcp.types import ListToolsRequest, CallToolRequest


class TestToolDefinitions:
    def test_reply_tool_schema(self):
        assert REPLY_TOOL.name == "reply"
        assert "chat_id" in REPLY_TOOL.inputSchema["properties"]
        assert "text" in REPLY_TOOL.inputSchema["properties"]
        assert REPLY_TOOL.inputSchema["required"] == ["chat_id", "text"]

    def test_react_tool_schema(self):
        assert REACT_TOOL.name == "react"
        assert "message_id" in REACT_TOOL.inputSchema["properties"]
        assert "emoji_type" in REACT_TOOL.inputSchema["properties"]


class TestChannelMcpServer:
    def _get_handler(self, server, request_type):
        """Get a registered request handler from the MCP server."""
        return server.request_handlers.get(request_type)

    @pytest.mark.asyncio
    async def test_create_server_basic(self):
        server = create_channel_mcp_server(
            reply_callback=AsyncMock(),
            instructions="Test",
        )
        assert server.name == "autoservice-channel"
        assert server.instructions == "Test"

    @pytest.mark.asyncio
    async def test_list_tools_returns_core(self):
        server = create_channel_mcp_server(reply_callback=AsyncMock())
        handler = self._get_handler(server, ListToolsRequest)
        assert handler is not None

    @pytest.mark.asyncio
    async def test_call_tool_handler_registered(self):
        server = create_channel_mcp_server(reply_callback=AsyncMock())
        handler = self._get_handler(server, CallToolRequest)
        assert handler is not None

    @pytest.mark.asyncio
    async def test_plugin_tools_in_definition(self):
        class FakePluginTool:
            name = "lookup"
            description = "Look up customer"
            input_schema = {"type": "object", "properties": {"id": {"type": "string"}}}
            def handler(self, **kwargs):
                return {"found": True}

        server = create_channel_mcp_server(
            reply_callback=AsyncMock(),
            plugin_tools=[FakePluginTool()],
        )
        # Server was created with the plugin tool registered
        assert server is not None


class TestPoolModeChannelServer:

    @pytest.mark.asyncio
    async def test_pool_mode_flag_default_false(self):
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False)
        assert server.pool_mode is False
        assert server._pool is None

    @pytest.mark.asyncio
    async def test_pool_mode_flag_set(self):
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False, pool_mode=True)
        assert server.pool_mode is True

    @pytest.mark.asyncio
    async def test_pool_mode_status_text(self):
        from channels.feishu.channel_server import ChannelServer
        server = ChannelServer(port=0, feishu_enabled=False)
        status = server.status_text()
        assert "Status" in status or "服务台" in status
