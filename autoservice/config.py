"""Backward-compatible shim — re-exports from socialware.config + L2 defaults.

Importing this module ensures L2 domain defaults are registered.
"""
import autoservice.domain_config  # noqa: F401 — register LANG_CONFIGS

from socialware.config import (  # noqa: F401
    load_config,
    get_domain_config,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)
from autoservice.domain_config import LANG_CONFIGS, DEFAULT_CONFIGS  # noqa: F401
