"""
Unified HTTP API client for mock and real modes.

Reads server info from .mock_server_info to connect to local mock server,
or uses api_config from product data to connect to remote API.
"""

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx


class APIClient:
    """HTTP client for API calls."""

    def __init__(self, domain: str, base_url: Optional[str] = None, timeout: float = 10.0):
        """
        Initialize API client.

        Args:
            domain: Domain name ('marketing', 'customer-service')
            base_url: Override base URL. If None, reads from .mock_server_info
            timeout: Request timeout in seconds
        """
        self.domain = domain
        self.timeout = timeout
        self._base_url = base_url

    @property
    def base_url(self) -> str:
        if self._base_url:
            return self._base_url
        # Read from mock server info
        domain_dir = self.domain.replace('-', '_')
        info_path = Path(f".autoservice/database/{domain_dir}/.mock_server_info")
        if info_path.exists():
            info = json.loads(info_path.read_text())
            return info.get("url", "http://localhost:8100")
        return "http://localhost:8100"

    def get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Execute GET request."""
        url = f"{self.base_url}{endpoint}"
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                url += "?" + urlencode(clean_params)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url)
            return resp.json()

    def post(self, endpoint: str, data: dict) -> dict:
        """Execute POST request."""
        url = f"{self.base_url}{endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=data)
            return resp.json()

    def put(self, endpoint: str, data: dict) -> dict:
        """Execute PUT request."""
        url = f"{self.base_url}{endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.put(url, json=data)
            return resp.json()

    # --- Convenience methods ---

    def query_customer(self, identifier: str) -> dict:
        return self.get(f"/api/v1/customers/{identifier}")

    def query_subscriptions(self, customer_id: str, service_name: str = None) -> dict:
        if service_name:
            return self.get(f"/api/v1/customers/{customer_id}/subscriptions/{service_name}")
        return self.get(f"/api/v1/customers/{customer_id}/subscriptions")

    def query_billing(self, customer_id: str, start_date: str = None, end_date: str = None) -> dict:
        return self.get(f"/api/v1/customers/{customer_id}/billing", {
            "start_date": start_date, "end_date": end_date,
        })

    def query_purchases(self, customer_id: str, limit: int = 10) -> dict:
        return self.get(f"/api/v1/customers/{customer_id}/purchases", {"limit": limit})

    def query_order(self, order_id: str) -> dict:
        return self.get(f"/api/v1/orders/{order_id}")

    def query_pricing(self, product_id: str, customer_tier: str = None, user_count: int = None) -> dict:
        return self.get(f"/api/v1/products/{product_id}/pricing", {
            "customer_tier": customer_tier, "user_count": user_count,
        })

    def query_feature(self, product_id: str, feature_name: str) -> dict:
        return self.get(f"/api/v1/products/{product_id}/features/{feature_name}")

    def query_services(self, category: str = None) -> dict:
        return self.get("/api/v1/services", {"category": category})

    def check_permission(self, action: str, product_id: str, domain: str = None) -> dict:
        return self.post("/api/v1/permissions/check", {
            "action": action,
            "product_id": product_id,
            "domain": domain or self.domain,
        })

    def request_refund(self, customer_id: str, transaction_id: str, amount: float, reason: str) -> dict:
        return self.post("/api/v1/refunds", {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "amount": amount,
            "reason": reason,
        })

    def change_subscription(self, subscription_id: str, action: str, effective_date: str = None) -> dict:
        return self.put(f"/api/v1/subscriptions/{subscription_id}", {
            "action": action,
            "effective_date": effective_date,
        })

    def health_check(self) -> dict:
        return self.get("/health")


def format_api_response(response: dict, endpoint: str = "", language: str = "zh") -> str:
    """Format API response for conversation display."""
    mode = response.get("mode", "mock").capitalize()
    success = response.get("success", False)

    if language == "en":
        status = "Success" if success else "Failed"
        lines = [f"[System Query Result - {mode}]"]
        if endpoint:
            lines.append(f"Endpoint: {endpoint}")
        lines.append(f"Status: {status}")
        if success:
            data = response.get("data", {})
            lines.append(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
        else:
            lines.append(f"Error: {response.get('error', 'Unknown error')}")
    else:
        status = "成功" if success else "失败"
        lines = [f"【系统查询结果 - {mode}】"]
        if endpoint:
            lines.append(f"接口: {endpoint}")
        lines.append(f"状态: {status}")
        if success:
            data = response.get("data", {})
            lines.append(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
        else:
            lines.append(f"错误: {response.get('error', '未知错误')}")

    lines.append("---")
    return "\n".join(lines)


def format_permission_response(response: dict, language: str = "zh") -> str:
    """Format permission check response for conversation display."""
    if response.get("success") and response.get("data", {}).get("display"):
        return response["data"]["display"]
    data = response.get("data", {})
    if language == "en":
        return f"[Permission Check Result]\nAction: {data.get('action', '?')}\nStatus: {'Allowed' if data.get('allowed') else 'Denied'}\nNote: {data.get('reason', '?')}\n---"
    return f"【权限检查结果】\n操作: {data.get('action', '?')}\n状态: {'允许' if data.get('allowed') else '拒绝'}\n说明: {data.get('reason', '?')}\n---"
