"""
API Interface abstraction layer for system queries.

Supports both mock mode (AI-generated responses) and real API calls.
"""

import json
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class APIResponse:
    """Standardized API response container."""
    success: bool
    data: dict
    endpoint: str
    is_mock: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None

    def to_display_block(self) -> str:
        """Format response as display block for conversation."""
        mode = "Mock" if self.is_mock else "Real"
        status = "Success" if self.success else "Error"

        lines = [
            f"【系统查询结果 - {mode}】",
            f"接口: {self.endpoint}",
            f"状态: {status}",
        ]

        if self.success:
            lines.append(f"响应: {json.dumps(self.data, ensure_ascii=False, indent=2)}")
        else:
            lines.append(f"错误: {self.error}")

        lines.append("---")
        return "\n".join(lines)


@dataclass
class APIInterface:
    """Definition of a system API interface."""
    name: str
    description: str
    endpoint: str
    method: str = "GET"
    params: list = field(default_factory=list)
    response_fields: list = field(default_factory=list)
    mock_enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, data: dict) -> 'APIInterface':
        """Create APIInterface from dictionary."""
        return cls(
            name=name,
            description=data.get('description', ''),
            endpoint=data.get('endpoint', ''),
            method=data.get('method', 'GET'),
            params=data.get('params', []),
            response_fields=data.get('response_fields', []),
            mock_enabled=data.get('mock_enabled', True)
        )


class APIQueryEngine:
    """
    Engine for executing API queries.

    In mock mode, returns a prompt for Claude to generate mock data.
    In real mode, executes HTTP requests to actual endpoints.
    """

    def __init__(self, mode: str = "mock", base_url: Optional[str] = None):
        """
        Initialize query engine.

        Args:
            mode: "mock" | "real" | "hybrid"
            base_url: Base URL for real API calls
        """
        self.mode = mode
        self.base_url = base_url

    def build_query_prompt(
        self,
        interface: APIInterface,
        params: dict,
        context: Optional[dict] = None
    ) -> str:
        """
        Build a prompt for mock data generation.

        Args:
            interface: The API interface definition
            params: Query parameters
            context: Additional context (product info, etc.)

        Returns:
            Prompt string for Claude to generate mock response
        """
        param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
        endpoint_with_params = interface.endpoint
        for k, v in params.items():
            endpoint_with_params = endpoint_with_params.replace(f"{{{k}}}", str(v))

        prompt_parts = [
            f"请为以下 API 查询生成模拟响应数据：",
            f"",
            f"**接口**: {interface.name}",
            f"**描述**: {interface.description}",
            f"**端点**: {interface.method} {endpoint_with_params}",
            f"**参数**: {param_str}",
            f"**预期响应字段**: {', '.join(interface.response_fields)}",
        ]

        if context:
            prompt_parts.extend([
                f"",
                f"**上下文信息**:",
                f"- 产品: {context.get('product_name', 'N/A')}",
                f"- 客户: {context.get('customer_id', 'N/A')}",
            ])

        prompt_parts.extend([
            f"",
            f"请生成合理的模拟数据，确保：",
            f"1. 数据与上下文一致",
            f"2. 使用中文",
            f"3. 返回 JSON 格式",
        ])

        return "\n".join(prompt_parts)

    def format_mock_response(
        self,
        interface: APIInterface,
        params: dict,
        mock_data: dict
    ) -> APIResponse:
        """
        Format mock data as APIResponse.

        Args:
            interface: The API interface definition
            params: Query parameters used
            mock_data: The mock data generated

        Returns:
            Formatted APIResponse
        """
        endpoint_with_params = interface.endpoint
        for k, v in params.items():
            endpoint_with_params = endpoint_with_params.replace(f"{{{k}}}", str(v))

        return APIResponse(
            success=True,
            data=mock_data,
            endpoint=f"{interface.method} {endpoint_with_params}",
            is_mock=True
        )


# Common API interface templates
COMMON_INTERFACES = {
    "user_info": APIInterface(
        name="user_info",
        description="查询用户基本信息",
        endpoint="/api/user/{user_id}",
        method="GET",
        params=["user_id"],
        response_fields=["name", "phone", "email", "account_status", "vip_level"],
        mock_enabled=True
    ),
    "subscription_check": APIInterface(
        name="subscription_check",
        description="检查用户订阅状态",
        endpoint="/api/user/{user_id}/subscriptions/{service_name}",
        method="GET",
        params=["user_id", "service_name"],
        response_fields=["is_subscribed", "start_date", "end_date", "auto_renew", "monthly_fee"],
        mock_enabled=True
    ),
    "billing_history": APIInterface(
        name="billing_history",
        description="查询用户账单历史",
        endpoint="/api/user/{user_id}/billing",
        method="GET",
        params=["user_id", "start_date", "end_date"],
        response_fields=["transactions", "total_amount", "pending_charges"],
        mock_enabled=True
    ),
    "purchase_history": APIInterface(
        name="purchase_history",
        description="查询用户购买记录",
        endpoint="/api/user/{user_id}/purchases",
        method="GET",
        params=["user_id", "limit"],
        response_fields=["purchases", "total_spent", "last_purchase_date"],
        mock_enabled=True
    ),
    "service_list": APIInterface(
        name="service_list",
        description="查询可用服务列表",
        endpoint="/api/services",
        method="GET",
        params=["category"],
        response_fields=["services", "total_count"],
        mock_enabled=True
    ),
}


def get_interface(name: str, product_interfaces: Optional[dict] = None) -> Optional[APIInterface]:
    """
    Get API interface by name.

    First checks product-specific interfaces, then falls back to common interfaces.

    Args:
        name: Interface name
        product_interfaces: Product-specific interface definitions

    Returns:
        APIInterface if found, None otherwise
    """
    if product_interfaces and name in product_interfaces:
        return APIInterface.from_dict(name, product_interfaces[name])

    return COMMON_INTERFACES.get(name)
