"""
Plugin loader — declarative plugin.yaml discovery and registration.

Scans plugins/*/plugin.yaml, resolves handler references to actual
Python callables, and returns Plugin objects ready for MCP tool
registration (channel) and FastAPI route mounting (web server).
"""

import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yaml

from socialware.mock_db import MockDB


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PluginTool:
    """An MCP tool declared by a plugin."""
    name: str
    description: str
    handler: Callable
    input_schema: dict
    plugin_name: str


@dataclass
class PluginRoute:
    """An HTTP route declared by a plugin."""
    path: str
    method: str  # GET, POST, PUT, DELETE
    handler: Callable
    plugin_name: str


@dataclass
class Plugin:
    """A fully loaded plugin, ready for registration."""
    name: str
    version: str
    description: str
    mode: str  # "mock" | "real"
    installer: str
    tools: list[PluginTool]
    routes: list[PluginRoute]
    references: list[Path]
    db: Optional[MockDB]
    plugin_dir: Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _import_module_from_path(module_name: str, file_path: Path):
    """Import a Python module from an absolute file path using importlib."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_handler(plugin_dir: Path, handler_ref: str, plugin_name: str) -> Callable:
    """
    Resolve a handler reference like "tools.crm_lookup" to a callable.

    handler_ref format: "{module}.{function}"
    Example: "tools.crm_lookup" -> plugins/crm/tools.py :: crm_lookup
    """
    parts = handler_ref.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid handler reference '{handler_ref}' — "
            f"expected 'module.function' format"
        )
    module_name, func_name = parts
    file_path = plugin_dir / f"{module_name}.py"

    if not file_path.exists():
        raise FileNotFoundError(
            f"Handler module not found: {file_path}"
        )

    # Use a namespaced module name to avoid collisions between plugins
    qualified_name = f"socialware.plugins.{plugin_name}.{module_name}"

    # Reuse already-imported module if available
    if qualified_name in sys.modules:
        module = sys.modules[qualified_name]
    else:
        module = _import_module_from_path(qualified_name, file_path)

    func = getattr(module, func_name, None)
    if func is None:
        raise AttributeError(
            f"Function '{func_name}' not found in {file_path}"
        )
    if not callable(func):
        raise TypeError(
            f"'{handler_ref}' resolved to a non-callable object"
        )
    return func


def _seed_db(db: MockDB, seed_data):
    """
    Seed a mock database with initial data loaded from JSON.

    seed_data can be:
    - a list  -> treated as {"customers": list}
    - a dict  -> keys are table names (customers, products, subscriptions)
    """
    if isinstance(seed_data, list):
        seed_data = {"customers": seed_data}

    for customer in seed_data.get("customers", []):
        db.upsert_customer(customer)

    for product in seed_data.get("products", []):
        db.upsert_product(product)

    for sub in seed_data.get("subscriptions", []):
        db.add_subscription(sub)


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------

def load_plugin(plugin_dir: Path) -> Plugin:
    """
    Load a single plugin from its directory.

    Reads plugin.yaml, resolves all handler references, and optionally
    initializes a mock database with seed data.
    """
    yaml_path = plugin_dir / "plugin.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"No plugin.yaml in {plugin_dir}")

    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    name = cfg.get("name", plugin_dir.name)
    version = cfg.get("version", "0.0.0")
    description = cfg.get("description", "")
    mode = cfg.get("mode", "mock")
    installer = cfg.get("installer", "")

    # --- Resolve MCP tools ---
    tools: list[PluginTool] = []
    for tool_cfg in cfg.get("mcp_tools", []):
        handler = _resolve_handler(
            plugin_dir, tool_cfg["handler"], name
        )
        tools.append(PluginTool(
            name=tool_cfg["name"],
            description=tool_cfg.get("description", ""),
            handler=handler,
            input_schema=tool_cfg.get("input_schema", {}),
            plugin_name=name,
        ))

    # --- Resolve HTTP routes ---
    routes: list[PluginRoute] = []
    for route_cfg in cfg.get("http_routes", []):
        handler = _resolve_handler(
            plugin_dir, route_cfg["handler"], name
        )
        routes.append(PluginRoute(
            path=route_cfg["path"],
            method=route_cfg.get("method", "GET").upper(),
            handler=handler,
            plugin_name=name,
        ))

    # --- Resolve reference files ---
    references: list[Path] = []
    for ref in cfg.get("references", []):
        ref_path = plugin_dir / ref
        if ref_path.exists():
            references.append(ref_path)

    # --- Initialize mock DB if needed ---
    db: Optional[MockDB] = None
    mock_cfg = cfg.get("mock_server", {})
    if mode == "mock" and mock_cfg:
        db_path = mock_cfg.get("database", f".autoservice/database/{name}/mock.db")
        db = MockDB(db_path)

        seed_file = mock_cfg.get("seed_data")
        if seed_file:
            seed_path = plugin_dir / seed_file
            if seed_path.exists():
                with open(seed_path) as f:
                    seed_data = json.load(f)
                _seed_db(db, seed_data)

    return Plugin(
        name=name,
        version=version,
        description=description,
        mode=mode,
        installer=installer,
        tools=tools,
        routes=routes,
        references=references,
        db=db,
        plugin_dir=plugin_dir,
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(plugins_dir: str | Path = "plugins") -> list[Plugin]:
    """
    Discover and load all plugins from the given directory.

    Scans for subdirectories containing plugin.yaml. Directories starting
    with "." are skipped. On failure, logs the error and continues with
    the remaining plugins.
    """
    plugins_path = Path(plugins_dir)
    if not plugins_path.is_dir():
        print(f"  plugins directory not found: {plugins_path}")
        return []

    loaded: list[Plugin] = []

    for child in sorted(plugins_path.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue

        yaml_path = child / "plugin.yaml"
        if not yaml_path.exists():
            continue

        try:
            plugin = load_plugin(child)
            loaded.append(plugin)
            tool_count = len(plugin.tools)
            route_count = len(plugin.routes)
            print(
                f"  [ok] {plugin.name} v{plugin.version} "
                f"({tool_count} tools, {route_count} routes, mode={plugin.mode})"
            )
        except Exception:
            print(f"  [FAIL] {child.name} -- failed to load:")
            traceback.print_exc()

    return loaded
