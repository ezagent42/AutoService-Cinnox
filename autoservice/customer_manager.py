"""
Customer management module with cold-start support.

Handles:
- Customer lookup by phone/ID
- Cold-start customer creation
- Customer information updates after calls
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from autoservice.core import generate_id, sanitize_name, ensure_dir
from autoservice.config import get_domain_config


class CustomerManager:
    """
    Manages customer records with support for cold-start scenarios.
    """

    def __init__(self, domain: str, config: Optional[dict] = None):
        """
        Initialize customer manager.

        Args:
            domain: Domain name ('marketing', 'customer-service')
            config: Optional domain configuration
        """
        self.domain = domain
        self.config = config or get_domain_config(domain)
        self.base_path = Path(self.config['database_path']) / 'customers'
        ensure_dir(self.base_path)

    def lookup_by_phone(self, phone: str) -> Tuple[Optional[dict], Optional[Path]]:
        """
        Look up customer by phone number.

        Args:
            phone: Phone number to search

        Returns:
            Tuple of (customer_data, customer_dir_path) or (None, None) if not found
        """
        if not self.base_path.exists():
            return None, None

        for customer_dir in self.base_path.iterdir():
            if not customer_dir.is_dir():
                continue

            info_file = customer_dir / 'info.json'
            if not info_file.exists():
                continue

            with open(info_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('phone') == phone or data.get('phone_number') == phone:
                    return data, customer_dir

        return None, None

    def lookup_by_id(self, customer_id: str) -> Tuple[Optional[dict], Optional[Path]]:
        """
        Look up customer by ID.

        Args:
            customer_id: Customer ID to search

        Returns:
            Tuple of (customer_data, customer_dir_path) or (None, None) if not found
        """
        if not self.base_path.exists():
            return None, None

        for customer_dir in self.base_path.iterdir():
            if not customer_dir.is_dir():
                continue

            # Check if ID matches directory prefix
            if customer_dir.name.startswith(customer_id):
                info_file = customer_dir / 'info.json'
                if info_file.exists():
                    with open(info_file, 'r', encoding='utf-8') as f:
                        return json.load(f), customer_dir

            # Also check _id field in info.json
            info_file = customer_dir / 'info.json'
            if info_file.exists():
                with open(info_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('_id') == customer_id:
                        return data, customer_dir

        return None, None

    def lookup_by_name(self, name: str) -> Tuple[Optional[dict], Optional[Path]]:
        """
        Look up customer by name (partial match).

        Args:
            name: Customer name to search

        Returns:
            Tuple of (customer_data, customer_dir_path) or (None, None) if not found
        """
        if not self.base_path.exists():
            return None, None

        for customer_dir in self.base_path.iterdir():
            if not customer_dir.is_dir():
                continue

            info_file = customer_dir / 'info.json'
            if not info_file.exists():
                continue

            with open(info_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                customer_name = data.get('name', '')
                if name in customer_name or customer_name in name:
                    return data, customer_dir

        return None, None

    def create_cold_start_customer(
        self,
        phone: str,
        initial_data: Optional[dict] = None
    ) -> Tuple[dict, Path]:
        """
        Create a cold-start customer record.

        This creates a minimal customer record that can be enriched during the call.

        Args:
            phone: Phone number (used as primary identifier)
            initial_data: Optional initial data to include

        Returns:
            Tuple of (customer_data, customer_dir_path)
        """
        customer_id = generate_id(phone)
        folder_name = f"{customer_id}_{sanitize_name(phone)}"
        customer_dir = ensure_dir(self.base_path / folder_name)

        data = {
            '_id': customer_id,
            '_type': 'customer',
            '_created': datetime.now().isoformat(),
            '_cold_start': True,
            'phone': phone,
            'name': f"来电客户_{phone[-4:]}",  # Temporary name
            'type': 'unknown',
            'interaction_history': [],
            'collected_info': {},
        }

        if initial_data:
            data.update(initial_data)

        # Save initial record
        with open(customer_dir / 'info.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._write_readme(customer_dir, data)

        return data, customer_dir

    def update_customer(
        self,
        customer_dir: Path,
        updates: dict,
        session_info: Optional[dict] = None
    ) -> dict:
        """
        Update customer information after a call.

        Args:
            customer_dir: Path to customer directory
            updates: Dictionary of fields to update
            session_info: Optional session information to add to history

        Returns:
            Updated customer data
        """
        info_file = customer_dir / 'info.json'

        with open(info_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Update fields
        data['_updated'] = datetime.now().isoformat()

        for key, value in updates.items():
            if not key.startswith('_'):
                data[key] = value

        # Add session to interaction history
        if session_info:
            if 'interaction_history' not in data:
                data['interaction_history'] = []
            data['interaction_history'].append({
                'session_id': session_info.get('session_id'),
                'timestamp': datetime.now().isoformat(),
                'type': session_info.get('type', 'call'),
                'summary': session_info.get('summary', ''),
                'outcome': session_info.get('outcome', ''),
            })

        # Mark as no longer cold-start if name was updated
        if 'name' in updates and updates['name'] != data.get('name'):
            data['_cold_start'] = False

        # Save updated record
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self._write_readme(customer_dir, data)

        return data

    def get_or_create(
        self,
        phone: Optional[str] = None,
        customer_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> Tuple[dict, Path, bool]:
        """
        Get existing customer or create cold-start record.

        Args:
            phone: Phone number
            customer_id: Customer ID
            name: Customer name

        Returns:
            Tuple of (customer_data, customer_dir_path, is_new)
        """
        # Try to find existing customer
        if customer_id:
            data, path = self.lookup_by_id(customer_id)
            if data:
                return data, path, False

        if phone:
            data, path = self.lookup_by_phone(phone)
            if data:
                return data, path, False

        if name:
            data, path = self.lookup_by_name(name)
            if data:
                return data, path, False

        # Create cold-start customer if phone provided
        if phone:
            data, path = self.create_cold_start_customer(phone)
            return data, path, True

        raise ValueError("无法创建客户记录：需要至少提供电话号码")

    def _write_readme(self, customer_dir: Path, data: dict):
        """Write human-readable README for customer."""
        with open(customer_dir / 'README.md', 'w', encoding='utf-8') as f:
            name = data.get('name', 'Unknown')
            f.write(f"# {name}\n\n")

            if data.get('_cold_start'):
                f.write("**[冷启动客户 - 信息待完善]**\n\n")

            for key, value in data.items():
                if key.startswith('_'):
                    continue
                if key == 'interaction_history':
                    f.write(f"## 交互历史\n\n")
                    for item in value:
                        f.write(f"- {item.get('timestamp', 'N/A')}: {item.get('summary', 'N/A')}\n")
                    f.write("\n")
                elif isinstance(value, list):
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
