"""
Permission and workflow control module.

Handles:
- Permission checking for operator actions
- Workflow/approval process definitions
- Action authorization
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class PermissionLevel(Enum):
    """Permission levels for actions."""
    APPROVE_IMMEDIATELY = "approve_immediately"  # Can approve right away
    REQUIRES_SUPERVISOR = "requires_supervisor"   # Need supervisor approval
    REQUIRES_PROCESS = "requires_process"         # Need to follow a formal process
    FORBIDDEN = "forbidden"                       # Not allowed at all


@dataclass
class PermissionCheck:
    """Result of a permission check."""
    action: str
    level: PermissionLevel
    allowed: bool
    reason: str
    workflow: Optional[str] = None  # Workflow to follow if not immediately allowed
    conditions: List[str] = field(default_factory=list)  # Conditions that apply

    def to_display_block(self) -> str:
        """Format permission check result for conversation display."""
        status_map = {
            PermissionLevel.APPROVE_IMMEDIATELY: "✓ 可立即批准",
            PermissionLevel.REQUIRES_SUPERVISOR: "⚠ 需要主管审批",
            PermissionLevel.REQUIRES_PROCESS: "⚠ 需要走流程",
            PermissionLevel.FORBIDDEN: "✗ 禁止操作",
        }

        lines = [
            f"【权限检查结果】",
            f"操作: {self.action}",
            f"状态: {status_map.get(self.level, '未知')}",
            f"说明: {self.reason}",
        ]

        if self.workflow:
            lines.append(f"流程: {self.workflow}")

        if self.conditions:
            lines.append(f"条件: {', '.join(self.conditions)}")

        lines.append("---")
        return "\n".join(lines)


@dataclass
class OperatorPermissions:
    """Permission configuration for an operator/product combination."""
    can_approve_immediately: List[str] = field(default_factory=list)
    requires_supervisor: List[str] = field(default_factory=list)
    requires_process: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> 'OperatorPermissions':
        """Create from dictionary."""
        return cls(
            can_approve_immediately=data.get('can_approve_immediately', []),
            requires_supervisor=data.get('requires_supervisor', []),
            requires_process=data.get('requires_process', []),
            forbidden=data.get('forbidden', []),
        )

    def check_permission(self, action: str) -> PermissionCheck:
        """
        Check permission for a specific action.

        Args:
            action: The action to check (e.g., "退款100元", "延期还款7天")

        Returns:
            PermissionCheck result
        """
        # Check forbidden first
        for rule in self.forbidden:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.FORBIDDEN,
                    allowed=False,
                    reason=f"此操作被禁止: {rule}",
                )

        # Check requires_process
        for rule in self.requires_process:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.REQUIRES_PROCESS,
                    allowed=False,
                    reason=f"此操作需要走正式流程: {rule}",
                    workflow="请引导客户提交正式申请，或记录工单后续跟进",
                )

        # Check requires_supervisor
        for rule in self.requires_supervisor:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.REQUIRES_SUPERVISOR,
                    allowed=False,
                    reason=f"此操作需要主管审批: {rule}",
                    workflow="请告知客户需要主管审批，预计X小时内回复",
                )

        # Check can_approve_immediately
        for rule in self.can_approve_immediately:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.APPROVE_IMMEDIATELY,
                    allowed=True,
                    reason=f"在权限范围内，可立即处理",
                    conditions=[rule],
                )

        # Default: unknown action, suggest caution
        return PermissionCheck(
            action=action,
            level=PermissionLevel.REQUIRES_SUPERVISOR,
            allowed=False,
            reason="未在预定义权限列表中，建议谨慎处理或请示主管",
        )

    def _matches_rule(self, action: str, rule: str) -> bool:
        """
        Check if action matches a rule.

        Rules can be:
        - Exact match: "退款"
        - Contains: "退款" matches "申请退款"
        - Threshold: "退款<100元" matches "退款50元"
        """
        # Simple contains check for now
        # More sophisticated parsing can be added later
        rule_lower = rule.lower()
        action_lower = action.lower()

        # Handle threshold rules like "退款<100元"
        if '<' in rule or '>' in rule or '<=' in rule or '>=' in rule:
            return self._matches_threshold_rule(action_lower, rule_lower)

        # Simple contains
        return rule_lower.replace(' ', '') in action_lower.replace(' ', '')

    def _matches_threshold_rule(self, action: str, rule: str) -> bool:
        """
        Match threshold rules like "退款<100元".

        This is a simplified implementation. For production,
        consider more robust parsing.
        """
        import re

        # Extract action type and amount from rule
        # Pattern: (action)(operator)(amount)(unit)
        rule_match = re.match(r'(.+?)([<>=]+)(\d+)(.*)', rule)
        if not rule_match:
            return rule in action

        rule_action = rule_match.group(1)
        operator = rule_match.group(2)
        threshold = int(rule_match.group(3))

        # Check if action mentions the same type
        if rule_action not in action:
            return False

        # Try to extract amount from action
        amount_match = re.search(r'(\d+)', action)
        if not amount_match:
            return False

        amount = int(amount_match.group(1))

        # Compare based on operator
        if operator == '<':
            return amount < threshold
        elif operator == '<=':
            return amount <= threshold
        elif operator == '>':
            return amount > threshold
        elif operator == '>=':
            return amount >= threshold
        elif operator == '=':
            return amount == threshold

        return False


# Default permission templates for common scenarios
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
    """
    Check permission for an action.

    Args:
        action: The action to check
        product_permissions: Product-specific permissions (from product data)
        domain: Domain name for default permissions

    Returns:
        PermissionCheck result
    """
    if product_permissions:
        permissions = OperatorPermissions.from_dict(product_permissions)
    else:
        permissions = get_default_permissions(domain)

    return permissions.check_permission(action)
