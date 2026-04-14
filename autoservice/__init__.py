"""AutoService — L2 customer service and sales application layer.

Re-exports L1 (socialware) framework APIs for backward compatibility,
plus L2 business-specific modules.
"""

# --- L1 re-exports (from socialware) for backward compatibility ---
from socialware.core import generate_id, sanitize_name, ensure_dir
from socialware.config import load_config
from socialware.database import save_record, list_records, print_results, get_output_dir
from socialware.importer import extract_from_docx, extract_from_xlsx, extract_from_pdf, import_file
from socialware.session import save_session, get_claude_session_id
from socialware.api_interfaces import APIResponse, APIInterface, APIQueryEngine
from socialware.mock_db import MockDB
from socialware.api_client import APIClient, format_api_response, format_permission_response
from socialware.logger import ConversationLogger
from socialware.permission import PermissionLevel, PermissionCheck, OperatorPermissions

# --- L2 domain modules (register defaults on import) ---
import autoservice.domain_config  # noqa: F401 — registers LANG_CONFIGS with L1

from autoservice.domain_config import LANG_CONFIGS, DEFAULT_CONFIGS, get_cs_config
from autoservice.domain_config import get_cs_config as get_domain_config
from autoservice.domain_session import (
    DOMAIN_PREFIXES, init_session, generate_session_id,
)
from autoservice.domain_permission import (
    DEFAULT_CUSTOMER_SERVICE_PERMISSIONS, DEFAULT_MARKETING_PERMISSIONS,
    get_default_permissions, check_permission,
)
from autoservice.api_interfaces import COMMON_INTERFACES, get_interface

# --- L2 business modules ---
from autoservice.customer_manager import CustomerManager
from autoservice.claude import query, pool_query

__all__ = [
    # L1 core (re-exported)
    'generate_id', 'sanitize_name', 'ensure_dir',
    'load_config', 'get_domain_config',
    'save_record', 'list_records', 'print_results', 'get_output_dir',
    'extract_from_docx', 'extract_from_xlsx', 'extract_from_pdf', 'import_file',
    'save_session', 'generate_session_id', 'get_claude_session_id', 'init_session',
    'APIResponse', 'APIInterface', 'APIQueryEngine',
    'COMMON_INTERFACES', 'get_interface',
    'CustomerManager',
    'PermissionLevel', 'PermissionCheck', 'OperatorPermissions',
    'check_permission', 'get_default_permissions',
    'MockDB',
    'APIClient', 'format_api_response', 'format_permission_response',
    'ConversationLogger',
    # L2 claude
    'query', 'pool_query',
    # L2 domain data
    'LANG_CONFIGS', 'DEFAULT_CONFIGS', 'get_cs_config',
    'DOMAIN_PREFIXES',
    'DEFAULT_CUSTOMER_SERVICE_PERMISSIONS', 'DEFAULT_MARKETING_PERMISSIONS',
]
