"""
Claude Agent - 简化版

仅加载代理配置，使用 .autoservice/.claude 作为配置目录
"""

import os
from pathlib import Path
from typing import AsyncIterator, Any
from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions


async def query(prompt: str, cwd: str = None) -> AsyncIterator[Any]:
    """
    执行 Claude Agent 查询

    Args:
        prompt: 查询提示词
        cwd: 工作目录，默认为当前目录

    Yields:
        原始消息对象
    """
    if cwd is None:
        cwd = str(Path.cwd())

    # 配置目录：.autoservice/.claude
    cwd_path = Path(cwd).absolute()
    plugin_path = cwd_path / ".autoservice" / ".claude"

    # 加载代理配置
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
        plugins=[{"type": "local", "path": str(plugin_path)}] if plugin_path.exists() else None,
        env=env,
    )

    async for message in sdk_query(prompt=prompt, options=options):
        yield message
