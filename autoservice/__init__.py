"""AutoService — AI-native customer service and sales bot framework."""

from autoservice.core import generate_id, sanitize_name, ensure_dir
from autoservice.config import load_config, get_domain_config
from autoservice.database import save_record, list_records, print_results, get_output_dir
from autoservice.importer import extract_from_docx, extract_from_xlsx, extract_from_pdf, import_file
from autoservice.session import save_session, generate_session_id, get_claude_session_id, init_session
from autoservice.api_interfaces import (
    APIResponse, APIInterface, APIQueryEngine,
    COMMON_INTERFACES, get_interface
)
from autoservice.customer_manager import CustomerManager
from autoservice.permission import (
    PermissionLevel, PermissionCheck, OperatorPermissions,
    check_permission, get_default_permissions
)
from autoservice.mock_db import MockDB
from autoservice.api_client import APIClient, format_api_response, format_permission_response
from autoservice.logger import ConversationLogger

__all__ = [
    # core
    'generate_id',
    'sanitize_name',
    'ensure_dir',
    # config
    'load_config',
    'get_domain_config',
    # database
    'save_record',
    'list_records',
    'print_results',
    'get_output_dir',
    # importer
    'extract_from_docx',
    'extract_from_xlsx',
    'extract_from_pdf',
    'import_file',
    # session
    'save_session',
    'generate_session_id',
    'get_claude_session_id',
    'init_session',
    # api_interfaces
    'APIResponse',
    'APIInterface',
    'APIQueryEngine',
    'COMMON_INTERFACES',
    'get_interface',
    # customer_manager
    'CustomerManager',
    # permission
    'PermissionLevel',
    'PermissionCheck',
    'OperatorPermissions',
    'check_permission',
    'get_default_permissions',
    # mock_db
    'MockDB',
    # api_client
    'APIClient',
    'format_api_response',
    'format_permission_response',
    # logger
    'ConversationLogger',
]
