"""
Database operations for record storage.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from socialware.core import generate_id, sanitize_name, ensure_dir
from socialware.config import get_domain_config


TYPE_MAP = {
    'product': 'products',
    'customer': 'customers',
    'operator': 'operators'
}


def get_output_dir(domain: str, item_type: str, config: Optional[dict] = None) -> Path:
    """Get output directory for item type in a domain."""
    if config is None:
        config = get_domain_config(domain)

    base_dir = Path(config['database_path'])
    return base_dir / TYPE_MAP[item_type]


def save_record(domain: str, record_type: str, data: dict, config: Optional[dict] = None) -> Path:
    """Save a record to the database.

    Args:
        domain: Domain name (e.g., 'marketing', 'customer-service')
        record_type: Type of record ('product', 'customer', 'operator')
        data: Record data dictionary (must contain 'name' key)
        config: Optional domain configuration

    Returns:
        Path to the created record directory
    """
    if config is None:
        config = get_domain_config(domain)

    output_dir = get_output_dir(domain, record_type, config)
    ensure_dir(output_dir)

    # Get name from various possible fields
    name = data.get('name', data.get('product_name', data.get('customer_name', 'unnamed')))
    item_id = generate_id(name)
    folder_name = f"{item_id}_{sanitize_name(name)}"

    item_dir = ensure_dir(output_dir / folder_name)

    # Add metadata
    data['_id'] = item_id
    data['_type'] = record_type
    data['_created'] = datetime.now().isoformat()

    # Save as JSON
    with open(item_dir / 'info.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Save as readable markdown
    with open(item_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(f"# {name}\n\n")
        for key, value in data.items():
            if not key.startswith('_'):
                if isinstance(value, list):
                    f.write(f"## {key.replace('_', ' ').title()}\n")
                    for item in value:
                        f.write(f"- {item}\n")
                    f.write("\n")
                elif isinstance(value, dict):
                    f.write(f"## {key.replace('_', ' ').title()}\n")
                    for k, v in value.items():
                        f.write(f"- **{k}**: {v}\n")
                    f.write("\n")
                else:
                    f.write(f"**{key.replace('_', ' ').title()}**: {value}\n\n")

    print(f"Saved to: {item_dir}")
    return item_dir


def list_records(domain: str, item_type: str = "all", verbose: bool = False,
                 config: Optional[dict] = None) -> dict:
    """List records of specified type."""
    if config is None:
        config = get_domain_config(domain)

    base_dir = Path(config['database_path'])
    results = {}

    types_to_list = [item_type] if item_type != "all" else ['product', 'customer', 'operator']

    for t in types_to_list:
        dir_path = base_dir / TYPE_MAP[t]
        items = []

        if dir_path.exists():
            for item_dir in sorted(dir_path.iterdir()):
                if item_dir.is_dir():
                    info_file = item_dir / 'info.json'
                    if info_file.exists():
                        with open(info_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if verbose:
                                items.append(data)
                            else:
                                items.append({
                                    'name': data.get('name', 'unnamed'),
                                    'id': data.get('_id', ''),
                                    'created': data.get('_created', '')
                                })

        results[t] = items

    return results


def get_record(domain: str, record_type: str, name_or_id: str,
               config: Optional[dict] = None) -> tuple[Optional[dict], Optional[Path]]:
    """Get a single record by name or ID."""
    if config is None:
        config = get_domain_config(domain)

    base_dir = Path(config['database_path'])
    type_dir = base_dir / TYPE_MAP[record_type]

    if not type_dir.exists():
        return None, None

    search_term = name_or_id.lower()

    for item_dir in type_dir.iterdir():
        if item_dir.is_dir():
            info_file = item_dir / 'info.json'
            if info_file.exists():
                with open(info_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if (data.get('_id', '').lower() == search_term or
                        data.get('name', '').lower() == search_term or
                        search_term in item_dir.name.lower()):
                        return data, item_dir

    return None, None


def update_record(domain: str, record_type: str, name_or_id: str,
                  updates: dict, config: Optional[dict] = None) -> Optional[Path]:
    """Update an existing record."""
    if config is None:
        config = get_domain_config(domain)

    data, item_dir = get_record(domain, record_type, name_or_id, config)

    if data is None or item_dir is None:
        return None

    for key, value in updates.items():
        if not key.startswith('_'):
            data[key] = value

    data['_updated'] = datetime.now().isoformat()

    with open(item_dir / 'info.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    name = data.get('name', 'unnamed')
    with open(item_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(f"# {name}\n\n")
        for key, value in data.items():
            if not key.startswith('_'):
                if isinstance(value, list):
                    f.write(f"## {key.replace('_', ' ').title()}\n")
                    for item in value:
                        f.write(f"- {item}\n")
                    f.write("\n")
                elif isinstance(value, dict):
                    f.write(f"## {key.replace('_', ' ').title()}\n")
                    for k, v in value.items():
                        f.write(f"- **{k}**: {v}\n")
                    f.write("\n")
                else:
                    f.write(f"**{key.replace('_', ' ').title()}**: {value}\n\n")

    return item_dir


def delete_record(domain: str, record_type: str, name_or_id: str,
                  config: Optional[dict] = None) -> bool:
    """Delete a record."""
    import shutil

    if config is None:
        config = get_domain_config(domain)

    data, item_dir = get_record(domain, record_type, name_or_id, config)

    if data is None or item_dir is None:
        return False

    shutil.rmtree(item_dir)
    return True


def print_results(results: dict, config: Optional[dict] = None, verbose: bool = False):
    """Print results in formatted output."""
    labels = {
        'product': 'Product',
        'customer': 'Customer',
        'operator': 'Operator'
    }

    if config and 'labels' in config:
        labels.update(config['labels'])

    for item_type, items in results.items():
        label = labels.get(item_type, item_type)
        print(f"\n## {label} ({len(items)})")
        print("-" * 40)

        if not items:
            print("(empty)")
            continue

        for i, item in enumerate(items, 1):
            if verbose:
                print(f"\n### {i}. {item.get('name', 'unnamed')}")
                for key, value in item.items():
                    if not key.startswith('_'):
                        if isinstance(value, list):
                            print(f"  {key}:")
                            for v in value:
                                print(f"    - {v}")
                        else:
                            print(f"  {key}: {value}")
            else:
                name = item.get('name', 'unnamed')
                item_id = item.get('id', '')
                created = item.get('created', '')[:10] if item.get('created') else ''
                print(f"  {i}. {name} (ID: {item_id}, created: {created})")
