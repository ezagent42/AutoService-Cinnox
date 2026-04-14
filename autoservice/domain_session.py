"""
Domain-specific session configuration for AutoService (L2).

Contains DOMAIN_PREFIXES mapping and convenience wrappers
around the L1 session framework.
"""

from typing import Optional

from socialware.session import (
    init_session as _init_session,
    generate_session_id as _generate_session_id,
)


# Domain type prefixes for customer service domains
DOMAIN_PREFIXES = {
    'customer-service': 'cs',
    'marketing': 'mk',
}


def init_session(domain: str, config: Optional[dict] = None) -> tuple[str, 'Path']:
    """Initialize a session with domain-specific prefix.

    Wraps socialware.session.init_session with DOMAIN_PREFIXES lookup.
    """
    prefix = DOMAIN_PREFIXES.get(domain, domain[:2])
    return _init_session(domain, config=config, prefix=prefix)


def generate_session_id(domain: str, claude_session_id: Optional[str] = None,
                        config: Optional[dict] = None) -> str:
    """Generate session ID with domain-specific prefix."""
    prefix = DOMAIN_PREFIXES.get(domain, domain[:2])
    return _generate_session_id(domain, claude_session_id, config, prefix=prefix)
