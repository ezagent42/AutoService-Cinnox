"""
Configuration loading for skill domains.

Supports multilingual configs via LANG_CONFIGS[lang][domain].
Default language: 'zh'. Supported: 'zh', 'en'.
"""

from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


# Supported languages
SUPPORTED_LANGUAGES = ('zh', 'en')
DEFAULT_LANGUAGE = 'zh'


# Language-specific configurations
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

# Backward-compatible alias: DEFAULT_CONFIGS points to Chinese configs
DEFAULT_CONFIGS = LANG_CONFIGS['zh']


def load_config(config_path: Path) -> dict:
    """Load configuration from a YAML file."""
    if yaml is None:
        raise ImportError("PyYAML is required to load config files. Install with: pip install pyyaml")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_domain_config(domain: str, config_path: Optional[Path] = None, language: Optional[str] = None) -> dict:
    """Get configuration for a domain.

    Args:
        domain: Domain name (e.g., 'marketing', 'customer-service')
        config_path: Optional path to config.yaml. If not provided, uses defaults.
        language: Language code ('zh' or 'en'). Defaults to 'zh'.

    Returns:
        Configuration dictionary
    """
    lang = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    # Try loading from file first
    if config_path and config_path.exists():
        try:
            config = load_config(config_path)
            config.setdefault('language', lang)
            return config
        except Exception:
            pass

    # Fall back to language-specific defaults
    lang_configs = LANG_CONFIGS.get(lang, LANG_CONFIGS[DEFAULT_LANGUAGE])
    if domain in lang_configs:
        return lang_configs[domain]

    # Generate a default config for unknown domains
    return {
        'domain': domain.replace('-', '_'),
        'language': lang,
        'database_path': f'.autoservice/database/{domain.replace("-", "_")}',
        'labels': {
            'product': 'Product',
            'customer': 'Customer',
            'operator': 'Operator'
        },
        'roles': {
            'assistant': 'assistant',
            'user': 'user',
            'assistant_label': 'Assistant',
            'user_label': 'User'
        },
        'session': {
            'title_prefix': f'{domain.title()} Session',
            'start_marker': '--- Session Started ---',
            'end_marker': '--- Session Ended ---'
        }
    }
