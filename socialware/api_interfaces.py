"""
API Interface abstraction layer for system queries.

Provides APIResponse, APIInterface, and APIQueryEngine framework classes.
Business-specific interface definitions (COMMON_INTERFACES) live in L2
(autoservice/api_interfaces.py).
"""

import json
from datetime import datetime
from typing import Optional
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
            f"[System Query Result - {mode}]",
            f"Endpoint: {self.endpoint}",
            f"Status: {status}",
        ]

        if self.success:
            lines.append(f"Response: {json.dumps(self.data, ensure_ascii=False, indent=2)}")
        else:
            lines.append(f"Error: {self.error}")

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
        self.mode = mode
        self.base_url = base_url

    def build_query_prompt(
        self,
        interface: APIInterface,
        params: dict,
        context: Optional[dict] = None
    ) -> str:
        """Build a prompt for mock data generation."""
        param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
        endpoint_with_params = interface.endpoint
        for k, v in params.items():
            endpoint_with_params = endpoint_with_params.replace(f"{{{k}}}", str(v))

        prompt_parts = [
            f"Generate mock API response data for the following query:",
            f"",
            f"**Interface**: {interface.name}",
            f"**Description**: {interface.description}",
            f"**Endpoint**: {interface.method} {endpoint_with_params}",
            f"**Parameters**: {param_str}",
            f"**Expected response fields**: {', '.join(interface.response_fields)}",
        ]

        if context:
            prompt_parts.extend([
                f"",
                f"**Context**:",
                f"- Product: {context.get('product_name', 'N/A')}",
                f"- Customer: {context.get('customer_id', 'N/A')}",
            ])

        prompt_parts.extend([
            f"",
            f"Please generate reasonable mock data ensuring:",
            f"1. Data is consistent with the context",
            f"2. Return JSON format",
        ])

        return "\n".join(prompt_parts)

    def format_mock_response(
        self,
        interface: APIInterface,
        params: dict,
        mock_data: dict
    ) -> APIResponse:
        """Format mock data as APIResponse."""
        endpoint_with_params = interface.endpoint
        for k, v in params.items():
            endpoint_with_params = endpoint_with_params.replace(f"{{{k}}}", str(v))

        return APIResponse(
            success=True,
            data=mock_data,
            endpoint=f"{interface.method} {endpoint_with_params}",
            is_mock=True
        )
