"""
Permission and workflow control framework.

Provides PermissionLevel, PermissionCheck, and OperatorPermissions base classes.
Business-specific permission defaults (DEFAULT_CUSTOMER_SERVICE_PERMISSIONS, etc.)
live in L2 (autoservice/domain_permission.py).
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class PermissionLevel(Enum):
    """Permission levels for actions."""
    APPROVE_IMMEDIATELY = "approve_immediately"
    REQUIRES_SUPERVISOR = "requires_supervisor"
    REQUIRES_PROCESS = "requires_process"
    FORBIDDEN = "forbidden"


@dataclass
class PermissionCheck:
    """Result of a permission check."""
    action: str
    level: PermissionLevel
    allowed: bool
    reason: str
    workflow: Optional[str] = None
    conditions: List[str] = field(default_factory=list)

    def to_display_block(self) -> str:
        """Format permission check result for conversation display."""
        status_map = {
            PermissionLevel.APPROVE_IMMEDIATELY: "✓ Approved",
            PermissionLevel.REQUIRES_SUPERVISOR: "⚠ Requires supervisor",
            PermissionLevel.REQUIRES_PROCESS: "⚠ Requires process",
            PermissionLevel.FORBIDDEN: "✗ Forbidden",
        }

        lines = [
            f"[Permission Check]",
            f"Action: {self.action}",
            f"Status: {status_map.get(self.level, 'Unknown')}",
            f"Reason: {self.reason}",
        ]

        if self.workflow:
            lines.append(f"Workflow: {self.workflow}")

        if self.conditions:
            lines.append(f"Conditions: {', '.join(self.conditions)}")

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
        """Check permission for a specific action."""
        for rule in self.forbidden:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.FORBIDDEN,
                    allowed=False,
                    reason=f"Forbidden: {rule}",
                )

        for rule in self.requires_process:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.REQUIRES_PROCESS,
                    allowed=False,
                    reason=f"Requires formal process: {rule}",
                    workflow="Submit formal application or create a ticket for follow-up",
                )

        for rule in self.requires_supervisor:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.REQUIRES_SUPERVISOR,
                    allowed=False,
                    reason=f"Requires supervisor approval: {rule}",
                    workflow="Escalate to supervisor for approval",
                )

        for rule in self.can_approve_immediately:
            if self._matches_rule(action, rule):
                return PermissionCheck(
                    action=action,
                    level=PermissionLevel.APPROVE_IMMEDIATELY,
                    allowed=True,
                    reason="Within authorized scope",
                    conditions=[rule],
                )

        return PermissionCheck(
            action=action,
            level=PermissionLevel.REQUIRES_SUPERVISOR,
            allowed=False,
            reason="Not in predefined permission list — recommend caution or supervisor consultation",
        )

    def _matches_rule(self, action: str, rule: str) -> bool:
        """Check if action matches a rule (contains or threshold)."""
        rule_lower = rule.lower()
        action_lower = action.lower()

        if '<' in rule or '>' in rule or '<=' in rule or '>=' in rule:
            return self._matches_threshold_rule(action_lower, rule_lower)

        return rule_lower.replace(' ', '') in action_lower.replace(' ', '')

    def _matches_threshold_rule(self, action: str, rule: str) -> bool:
        """Match threshold rules like "refund<100"."""
        rule_match = re.match(r'(.+?)([<>=]+)(\d+)(.*)', rule)
        if not rule_match:
            return rule in action

        rule_action = rule_match.group(1)
        operator = rule_match.group(2)
        threshold = int(rule_match.group(3))

        if rule_action not in action:
            return False

        amount_match = re.search(r'(\d+)', action)
        if not amount_match:
            return False

        amount = int(amount_match.group(1))

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
