"""
Plugin KB integration — lazy-loaded KB search and route query modules.

Provides in-process KB search and route query without subprocess overhead.
Plugin skills register their script paths; this module loads them on demand.
"""

import importlib.util
import time
from pathlib import Path


# ── Module-level state (lazy-loaded) ──────────────────────────────────────
_kb_mod = None
_route_mod = None

# Configurable paths (set by app.py)
_kb_search_paths: list[Path] = []
_route_query_paths: list[Path] = []


def configure(root: Path) -> None:
    """Set search paths for KB and route query scripts.

    Plugins can extend these paths by appending to the lists.
    """
    global _kb_search_paths, _route_query_paths
    _kb_search_paths = [
        root / ".claude" / "skills" / "knowledge-base" / "scripts" / "kb_search.py",
    ]
    _route_query_paths = [
        root / ".claude" / "skills" / "knowledge-base" / "scripts" / "route_query.py",
        root / ".autoservice" / ".claude" / "skills" / "knowledge-base" / "scripts" / "route_query.py",
    ]


def get_kb_search():
    """Lazy-load the KB search module."""
    global _kb_mod
    if _kb_mod is None:
        for p in _kb_search_paths:
            if p.exists():
                spec = importlib.util.spec_from_file_location("kb_search", p)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _kb_mod = mod
                break
    return _kb_mod


def get_route_query():
    """Lazy-load the route query module."""
    global _route_mod
    if _route_mod is None:
        for p in _route_query_paths:
            if p.exists():
                spec = importlib.util.spec_from_file_location("route_query", p)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _route_mod = mod
                break
    return _route_mod


def presearch_kb(
    user_text: str, top_k: int = 3, *, gate_cleared: bool = True
) -> tuple[str, int]:
    """Search KB before calling Claude and inject results into the prompt.

    Returns (augmented_prompt, hit_count).
    If KB unavailable or no results, returns (user_text, 0) unchanged.
    When gate_cleared is False, skip KB injection so the mandatory gate
    (customer identification) is not short-circuited by pre-fetched answers.
    """
    if not gate_cleared:
        return user_text, 0
    # Skip injection for very short inputs (greetings, single words)
    if len(user_text.strip()) < 12:
        return user_text, 0
    mod = get_kb_search()
    if mod is None:
        return user_text, 0
    try:
        t_search = time.perf_counter()
        results = mod.search(user_text, top_k=top_k)
        print(
            f"[timing] presearch: {time.perf_counter() - t_search:.3f}s -> {len(results)} hits",
            flush=True,
        )
        if not results:
            return user_text, 0
        parts = []
        for r in results:
            section = r.get("section", "")
            src = r["source_name"] + (f" | {section}" if section else "")
            parts.append(f"[{src}]\n{r['content'][:500]}")
        injected = "\n\n".join(parts)
        augmented = f"{user_text}\n\n---\nKB Context (pre-fetched):\n{injected}\n---"
        return augmented, len(results)
    except Exception as exc:
        print(f"[presearch] error: {exc}", flush=True)
        return user_text, 0
