"""Backward-compatible shim — re-exports from socialware.session + L2 domain session.

For domain-aware init_session/generate_session_id with DOMAIN_PREFIXES,
use autoservice.domain_session directly.
"""
from socialware.session import (  # noqa: F401
    get_claude_session_id,
    save_session,
)
from autoservice.domain_session import (  # noqa: F401
    DOMAIN_PREFIXES,
    init_session,
    generate_session_id,
)
