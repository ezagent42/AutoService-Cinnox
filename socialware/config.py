"""
Configuration loading mechanism.

Provides generic config loading from YAML files and domain config
resolution. Business-specific config data (LANG_CONFIGS, domain defaults)
lives in L2 (autoservice/domain_config.py).
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

# Registry for L2 domain config defaults.
# L2 populates this via register_domain_defaults() at import time.
_domain_defaults: dict[str, dict[str, dict]] = {}


def register_domain_defaults(lang_configs: dict[str, dict[str, dict]]):
    """Register domain config defaults from L2.

    Args:
        lang_configs: Mapping of language -> domain -> config dict.
            Example: {'zh': {'marketing': {...}, 'customer-service': {...}}}
    """
    _domain_defaults.update(lang_configs)


def load_config(config_path: Path) -> dict:
    """Load configuration from a YAML file."""
    if yaml is None:
        raise ImportError("PyYAML is required to load config files. Install with: pip install pyyaml")

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_domain_config(domain: str, config_path: Optional[Path] = None,
                      language: Optional[str] = None,
                      defaults: Optional[dict] = None) -> dict:
    """Get configuration for a domain.

    Resolution order:
    1. config_path YAML file (if provided and exists)
    2. Explicit defaults parameter
    3. Registered domain defaults (from L2 via register_domain_defaults)
    4. Auto-generated minimal config

    Args:
        domain: Domain name (e.g., 'marketing', 'customer-service')
        config_path: Optional path to config.yaml
        language: Language code ('zh' or 'en'). Defaults to 'zh'.
        defaults: Optional default config dict to use instead of registered defaults

    Returns:
        Configuration dictionary
    """
    lang = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    # 1. Try loading from file
    if config_path and config_path.exists():
        try:
            config = load_config(config_path)
            config.setdefault('language', lang)
            return config
        except Exception:
            pass

    # 2. Explicit defaults
    if defaults and domain in defaults:
        return defaults[domain]

    # 3. Registered domain defaults from L2
    lang_configs = _domain_defaults.get(lang, _domain_defaults.get(DEFAULT_LANGUAGE, {}))
    if domain in lang_configs:
        return lang_configs[domain]

    # 4. Auto-generated minimal config for unknown domains
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
