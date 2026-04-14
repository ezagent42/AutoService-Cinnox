"""Socialware — L1 base framework for social-channel AI applications.

Provides channel integration, plugin loading, configuration management,
session framework, and generic utilities. Language-agnostic and
domain-agnostic — usable for customer service, education, healthcare,
or any other vertical.
"""

# core utilities
from socialware.core import generate_id, sanitize_name, ensure_dir

# configuration mechanism
from socialware.config import load_config, get_domain_config

# data storage
from socialware.database import (
    save_record, list_records, get_record, update_record, delete_record,
    print_results, get_output_dir,
)
from socialware.mock_db import MockDB

# file import
from socialware.importer import (
    extract_from_docx, extract_from_xlsx, extract_from_pdf, import_file,
)

# session framework
from socialware.session import (
    save_session, generate_session_id, get_claude_session_id, init_session,
)

# API abstractions
from socialware.api_interfaces import APIResponse, APIInterface, APIQueryEngine
from socialware.api_client import APIClient, format_api_response, format_permission_response

# permission framework
from socialware.permission import PermissionLevel, PermissionCheck, OperatorPermissions

# plugin system
from socialware.plugin_loader import Plugin, PluginTool, PluginRoute, load_plugin, discover

# logging
from socialware.logger import ConversationLogger

# pool framework
from socialware.pool import PoolableClient, PoolConfig, PooledInstance, AsyncPool

__all__ = [
    # core
    'generate_id', 'sanitize_name', 'ensure_dir',
    # config
    'load_config', 'get_domain_config',
    # database
    'save_record', 'list_records', 'get_record', 'update_record', 'delete_record',
    'print_results', 'get_output_dir',
    'MockDB',
    # importer
    'extract_from_docx', 'extract_from_xlsx', 'extract_from_pdf', 'import_file',
    # session
    'save_session', 'generate_session_id', 'get_claude_session_id', 'init_session',
    # api
    'APIResponse', 'APIInterface', 'APIQueryEngine',
    'APIClient', 'format_api_response', 'format_permission_response',
    # permission
    'PermissionLevel', 'PermissionCheck', 'OperatorPermissions',
    # plugin
    'Plugin', 'PluginTool', 'PluginRoute', 'load_plugin', 'discover',
    # logger
    'ConversationLogger',
    # pool
    'PoolableClient', 'PoolConfig', 'PooledInstance', 'AsyncPool',
]
