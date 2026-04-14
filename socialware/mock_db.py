"""
SQLite mock database for local API serving.

Provides schema creation, CRUD operations, and data seeding
for the mock API server.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    type TEXT DEFAULT 'new',
    vip_level INTEGER DEFAULT 0,
    account_status TEXT DEFAULT 'active',
    company TEXT,
    role TEXT,
    industry TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    price TEXT,
    category TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    product_id TEXT,
    service_name TEXT NOT NULL,
    fee REAL DEFAULT 0,
    status TEXT DEFAULT 'active',
    start_date DATE,
    end_date DATE,
    auto_renew BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_customer ON subscriptions(customer_id);

CREATE TABLE IF NOT EXISTS billing_transactions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    type TEXT DEFAULT 'charge',
    description TEXT,
    amount REAL NOT NULL,
    date DATE,
    status TEXT DEFAULT 'completed',
    related_subscription_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX IF NOT EXISTS idx_billing_customer ON billing_transactions(customer_id);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    product TEXT,
    price REAL,
    status TEXT DEFAULT 'pending',
    delivery_carrier TEXT,
    delivery_tracking TEXT,
    delivery_eta DATE,
    payment_status TEXT DEFAULT 'pending',
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);

CREATE TABLE IF NOT EXISTS permission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT,
    domain TEXT NOT NULL,
    level TEXT NOT NULL,
    rule_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_pricing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    base_price REAL,
    volume_discount TEXT,
    special_offers_json TEXT,
    trial_options_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS product_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    is_available BOOLEAN DEFAULT 1,
    release_date DATE,
    tier_required TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL,
    period TEXT DEFAULT '月',
    category TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    params_json TEXT,
    response_json TEXT,
    mode TEXT DEFAULT 'mock',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class MockDB:
    """SQLite mock database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # --- Customer operations ---

    def upsert_customer(self, customer: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO customers
                (id, name, phone, email, type, vip_level, account_status, company, role, industry, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                customer.get('_id', customer.get('id', '')),
                customer.get('name', ''),
                customer.get('phone', ''),
                customer.get('email', ''),
                customer.get('type', 'new'),
                customer.get('vip_level', 0),
                customer.get('account_status', 'active'),
                customer.get('company', ''),
                customer.get('role', ''),
                customer.get('industry', ''),
                json.dumps(customer, ensure_ascii=False),
                customer.get('_created', datetime.now().isoformat()),
                datetime.now().isoformat(),
            ))

    def get_customer(self, identifier: str) -> Optional[dict]:
        """Get customer by ID or phone."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ? OR phone = ?",
                (identifier, identifier)
            ).fetchone()
            if row:
                return self._customer_to_dict(row)
        return None

    def _customer_to_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "email": row["email"],
            "type": row["type"],
            "vip_level": row["vip_level"],
            "account_status": row["account_status"],
            "company": row["company"],
            "role": row["role"],
            "industry": row["industry"],
            "created_at": row["created_at"],
        }

    # --- Product operations ---

    def upsert_product(self, product: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO products
                (id, name, description, price, category, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product.get('_id', product.get('id', '')),
                product.get('name', ''),
                product.get('description', ''),
                str(product.get('price', '')),
                product.get('category', ''),
                json.dumps(product, ensure_ascii=False),
                product.get('_created', datetime.now().isoformat()),
                datetime.now().isoformat(),
            ))

    def get_product(self, product_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if row:
                return dict(row)
        return None

    def get_product_full_data(self, product_id: str) -> Optional[dict]:
        """Get full product data including data_json."""
        with self._connect() as conn:
            row = conn.execute("SELECT data_json FROM products WHERE id = ?", (product_id,)).fetchone()
            if row and row["data_json"]:
                return json.loads(row["data_json"])
        return None

    # --- Subscription operations ---

    def add_subscription(self, sub: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO subscriptions
                (id, customer_id, product_id, service_name, fee, status, start_date, end_date, auto_renew)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sub.get('id', ''),
                sub.get('customer_id', ''),
                sub.get('product_id', ''),
                sub.get('service_name', ''),
                sub.get('fee', 0),
                sub.get('status', 'active'),
                sub.get('start_date', ''),
                sub.get('end_date', ''),
                sub.get('auto_renew', True),
            ))

    def get_subscriptions(self, customer_id: str, service_name: Optional[str] = None) -> list:
        with self._connect() as conn:
            if service_name:
                rows = conn.execute(
                    "SELECT * FROM subscriptions WHERE customer_id = ? AND service_name LIKE ?",
                    (customer_id, f"%{service_name}%")
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM subscriptions WHERE customer_id = ?",
                    (customer_id,)
                ).fetchall()
            return [dict(r) for r in rows]

    # --- Billing operations ---

    def add_billing_transaction(self, txn: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO billing_transactions
                (id, customer_id, type, description, amount, date, status, related_subscription_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                txn.get('id', ''),
                txn.get('customer_id', ''),
                txn.get('type', 'charge'),
                txn.get('description', ''),
                txn.get('amount', 0),
                txn.get('date', ''),
                txn.get('status', 'completed'),
                txn.get('related_subscription_id', ''),
            ))

    def get_billing(self, customer_id: str, start_date: str = None, end_date: str = None) -> dict:
        with self._connect() as conn:
            query = "SELECT * FROM billing_transactions WHERE customer_id = ?"
            params = [customer_id]
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY date DESC"
            rows = conn.execute(query, params).fetchall()
            transactions = [dict(r) for r in rows]
            total = sum(t.get('amount', 0) for t in transactions if t.get('status') == 'completed')
            pending = sum(t.get('amount', 0) for t in transactions if t.get('status') == 'pending')
            return {
                "transactions": transactions,
                "total_amount": total,
                "pending_charges": pending,
            }

    # --- Purchase/Order operations ---

    def add_order(self, order: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO orders
                (id, customer_id, product, price, status, delivery_carrier, delivery_tracking, delivery_eta, payment_status, date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.get('id', ''),
                order.get('customer_id', ''),
                order.get('product', ''),
                order.get('price', 0),
                order.get('status', 'pending'),
                order.get('delivery_carrier', ''),
                order.get('delivery_tracking', ''),
                order.get('delivery_eta', ''),
                order.get('payment_status', 'pending'),
                order.get('date', ''),
            ))

    def get_purchases(self, customer_id: str, limit: int = 10) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE customer_id = ? ORDER BY date DESC LIMIT ?",
                (customer_id, limit)
            ).fetchall()
            purchases = [dict(r) for r in rows]
            total_spent = sum(p.get('price', 0) for p in purchases)
            last_date = purchases[0].get('date', '') if purchases else ''
            return {
                "purchases": purchases,
                "total_spent": total_spent,
                "last_purchase_date": last_date,
            }

    def get_order(self, order_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row:
                order = dict(row)
                order["items"] = [{"name": order.get("product", ""), "quantity": 1, "price": order.get("price", 0)}]
                delivery_info = {}
                if order.get("delivery_carrier"):
                    delivery_info["carrier"] = order["delivery_carrier"]
                if order.get("delivery_tracking"):
                    delivery_info["tracking"] = order["delivery_tracking"]
                if order.get("delivery_eta"):
                    delivery_info["eta"] = order["delivery_eta"]
                order["delivery_info"] = delivery_info
                return order
        return None

    # --- Product pricing ---

    def set_product_pricing(self, pricing: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO product_pricing
                (product_id, base_price, volume_discount, special_offers_json, trial_options_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                pricing.get('product_id', ''),
                pricing.get('base_price', 0),
                pricing.get('volume_discount', ''),
                json.dumps(pricing.get('special_offers', []), ensure_ascii=False),
                json.dumps(pricing.get('trial_options', {}), ensure_ascii=False),
            ))

    def get_product_pricing(self, product_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM product_pricing WHERE product_id = ?",
                (product_id,)
            ).fetchone()
            if row:
                result = dict(row)
                result["special_offers"] = json.loads(result.get("special_offers_json", "[]"))
                result["trial_options"] = json.loads(result.get("trial_options_json", "{}"))
                return result
        return None

    # --- Product features ---

    def add_product_feature(self, feature: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO product_features
                (product_id, feature_name, is_available, release_date, tier_required)
                VALUES (?, ?, ?, ?, ?)
            """, (
                feature.get('product_id', ''),
                feature.get('feature_name', ''),
                feature.get('is_available', True),
                feature.get('release_date', ''),
                feature.get('tier_required', ''),
            ))

    def get_product_feature(self, product_id: str, feature_name: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM product_features WHERE product_id = ? AND feature_name LIKE ?",
                (product_id, f"%{feature_name}%")
            ).fetchone()
            if row:
                return dict(row)
        return None

    # --- Services ---

    def add_service(self, service: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO services
                (id, name, price, period, category, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                service.get('id', ''),
                service.get('name', ''),
                service.get('price', 0),
                service.get('period', '月'),
                service.get('category', ''),
                service.get('description', ''),
            ))

    def get_services(self, category: Optional[str] = None) -> dict:
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM services WHERE category LIKE ?",
                    (f"%{category}%",)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM services").fetchall()
            services = [dict(r) for r in rows]
            return {"services": services, "total_count": len(services)}

    # --- Permission rules ---

    def set_permission_rules(self, product_id: str, domain: str, rules: dict):
        """Set permission rules for a product."""
        with self._connect() as conn:
            # Clear existing rules for this product+domain
            conn.execute(
                "DELETE FROM permission_rules WHERE product_id = ? AND domain = ?",
                (product_id, domain)
            )
            for level, rule_list in rules.items():
                for rule_text in rule_list:
                    conn.execute(
                        "INSERT INTO permission_rules (product_id, domain, level, rule_text) VALUES (?, ?, ?, ?)",
                        (product_id, domain, level, rule_text)
                    )

    def get_permission_rules(self, product_id: str, domain: str) -> dict:
        """Get permission rules as a dict of level -> [rules]."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT level, rule_text FROM permission_rules WHERE product_id = ? AND domain = ?",
                (product_id, domain)
            ).fetchall()
            result = {
                "can_approve_immediately": [],
                "requires_supervisor": [],
                "requires_process": [],
                "forbidden": [],
            }
            for row in rows:
                level = row["level"]
                if level in result:
                    result[level].append(row["rule_text"])
            return result

    # --- Audit log ---

    def log_api_call(self, endpoint: str, method: str, params: dict = None, response: dict = None):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO api_audit_log (endpoint, method, params_json, response_json, mode)
                VALUES (?, ?, ?, ?, 'mock')
            """, (
                endpoint,
                method,
                json.dumps(params or {}, ensure_ascii=False),
                json.dumps(response or {}, ensure_ascii=False),
            ))
