"""
Business-specific API interface definitions for AutoService (L2).

Re-exports framework classes from socialware and defines
COMMON_INTERFACES with customer-service domain endpoints.
"""

from typing import Optional

from socialware.api_interfaces import APIResponse, APIInterface, APIQueryEngine  # noqa: F401


# Common API interface templates for customer service / marketing domains
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
    """Get API interface by name.

    First checks product-specific interfaces, then falls back to common interfaces.
    """
    if product_interfaces and name in product_interfaces:
        return APIInterface.from_dict(name, product_interfaces[name])

    return COMMON_INTERFACES.get(name)
