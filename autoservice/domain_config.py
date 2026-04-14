"""
Domain-specific configuration data for AutoService (L2).

Contains LANG_CONFIGS with business-specific domain defaults
for marketing and customer-service domains.

This module registers its defaults with the L1 config framework
at import time, so any call to socialware.config.get_domain_config()
will automatically find these defaults.
"""

from socialware.config import register_domain_defaults, get_domain_config as _get_domain_config


# Language-specific configurations for customer service domains
LANG_CONFIGS = {
    'zh': {
        'marketing': {
            'domain': 'marketing',
            'language': 'zh',
            'database_path': '.autoservice/database/marketing',
            'labels': {
                'product': '产品',
                'customer': '客户角色',
                'operator': '销售策略'
            },
            'roles': {
                'assistant': 'salesperson',
                'user': 'customer',
                'assistant_label': '销售员',
                'user_label': '客户'
            },
            'session': {
                'title_prefix': 'Sales Session',
                'start_marker': '--- 销售通话已开始 ---',
                'end_marker': '--- 销售通话已结束 ---'
            }
        },
        'customer-service': {
            'domain': 'customer_service',
            'language': 'zh',
            'database_path': '.autoservice/database/customer_service',
            'labels': {
                'product': '产品/服务',
                'customer': '客户角色',
                'operator': '客服策略'
            },
            'roles': {
                'assistant': 'agent',
                'user': 'customer',
                'assistant_label': '客服',
                'user_label': '客户'
            },
            'session': {
                'title_prefix': 'Customer Service Session',
                'start_marker': '--- 客服电话已接通 ---',
                'end_marker': '--- 客服电话已结束 ---'
            }
        }
    },
    'en': {
        'marketing': {
            'domain': 'marketing',
            'language': 'en',
            'database_path': '.autoservice/database/marketing',
            'labels': {
                'product': 'Product',
                'customer': 'Customer Persona',
                'operator': 'Sales Strategy'
            },
            'roles': {
                'assistant': 'salesperson',
                'user': 'customer',
                'assistant_label': 'Salesperson',
                'user_label': 'Customer'
            },
            'session': {
                'title_prefix': 'Sales Session',
                'start_marker': '--- Sales Call Started ---',
                'end_marker': '--- Sales Call Ended ---'
            }
        },
        'customer-service': {
            'domain': 'customer_service',
            'language': 'en',
            'database_path': '.autoservice/database/customer_service',
            'labels': {
                'product': 'Product/Service',
                'customer': 'Customer Persona',
                'operator': 'Service Strategy'
            },
            'roles': {
                'assistant': 'agent',
                'user': 'customer',
                'assistant_label': 'Agent',
                'user_label': 'Customer'
            },
            'session': {
                'title_prefix': 'Customer Service Session',
                'start_marker': '--- Service Call Connected ---',
                'end_marker': '--- Service Call Ended ---'
            }
        }
    }
}

# Backward-compatible alias
DEFAULT_CONFIGS = LANG_CONFIGS['zh']

# Register with L1 framework so get_domain_config() finds these defaults
register_domain_defaults(LANG_CONFIGS)


def get_cs_config(domain: str, config_path=None, language='zh') -> dict:
    """Get customer-service domain config with L2 defaults."""
    return _get_domain_config(domain, config_path, language)
