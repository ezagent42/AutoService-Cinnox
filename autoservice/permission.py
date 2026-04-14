"""Backward-compatible shim — re-exports from socialware.permission + L2 defaults."""
from socialware.permission import (  # noqa: F401
    PermissionLevel,
    PermissionCheck,
    OperatorPermissions,
)
from autoservice.domain_permission import (  # noqa: F401
    DEFAULT_CUSTOMER_SERVICE_PERMISSIONS,
    DEFAULT_MARKETING_PERMISSIONS,
    get_default_permissions,
    check_permission,
)
