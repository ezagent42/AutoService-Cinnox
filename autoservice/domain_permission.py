"""
Domain-specific permission defaults for AutoService (L2).

Contains DEFAULT_CUSTOMER_SERVICE_PERMISSIONS and DEFAULT_MARKETING_PERMISSIONS.
Wraps the L1 permission framework with business-specific defaults.
"""

from typing import Optional

from socialware.permission import (
    PermissionLevel,
    PermissionCheck,
    OperatorPermissions,
)


# Default permission templates for customer service
DEFAULT_CUSTOMER_SERVICE_PERMISSIONS = OperatorPermissions(
    can_approve_immediately=[
        "退款<100元",
        "延期还款<7天",
        "重置密码",
        "账户解锁",
        "补发短信验证码",
        "修改联系方式",
        "查询账单",
        "解释政策",
    ],
    requires_supervisor=[
        "退款>=100元",
        "延期还款>=7天",
        "账户注销",
        "VIP升级",
        "特殊优惠",
        "投诉升级",
    ],
    requires_process=[
        "大额赔偿",
        "法律相关",
        "媒体曝光",
        "批量退款",
    ],
    forbidden=[
        "透露其他用户信息",
        "承诺政策外优惠",
        "修改交易记录",
        "绕过安全验证",
    ],
)

# Default permission templates for marketing/sales
DEFAULT_MARKETING_PERMISSIONS = OperatorPermissions(
    can_approve_immediately=[
        "试用<30天",
        "折扣<10%",
        "延期付款<15天",
        "提供产品资料",
        "安排演示",
        "介绍报价",
    ],
    requires_supervisor=[
        "试用>=30天",
        "折扣>=10%",
        "定制开发",
        "特殊付款条件",
        "战略合作",
    ],
    requires_process=[
        "年度框架协议",
        "独家代理",
        "白标合作",
        "源码授权",
    ],
    forbidden=[
        "虚假承诺",
        "贬低竞品",
        "透露其他客户信息",
        "承诺未发布功能",
    ],
)


def get_default_permissions(domain: str) -> OperatorPermissions:
    """Get default permissions for a domain."""
    if domain == 'customer-service':
        return DEFAULT_CUSTOMER_SERVICE_PERMISSIONS
    elif domain == 'marketing':
        return DEFAULT_MARKETING_PERMISSIONS
    else:
        return OperatorPermissions()


def check_permission(
    action: str,
    product_permissions: Optional[dict] = None,
    domain: str = 'customer-service'
) -> PermissionCheck:
    """Check permission for an action with L2 domain defaults."""
    if product_permissions:
        permissions = OperatorPermissions.from_dict(product_permissions)
    else:
        permissions = get_default_permissions(domain)

    return permissions.check_permission(action)
