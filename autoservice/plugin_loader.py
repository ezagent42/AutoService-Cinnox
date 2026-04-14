"""Backward-compatible shim — re-exports from socialware.plugin_loader."""
from socialware.plugin_loader import (  # noqa: F401
    PluginTool, PluginRoute, Plugin,
    load_plugin, discover,
)
