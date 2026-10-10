"""OpenAI tool calling adapter with pre-execution safety gating."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional, Union

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    GatingDecisionType,
    InterceptionDecision,
)
from sidegate.gating.gate import RuntimeActionGate


class OpenAIToolGateAdapter:
    """Interception wrapper for OpenAI function calling and tool execution workflows."""

    def __init__(
        self,
        gate: Optional[RuntimeActionGate] = None,
        tool_dispatch_fn: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> None:
        self.gate = gate or RuntimeActionGate()
        self.tool_dispatch_fn = tool_dispatch_fn

    def intercept_and_dispatch(
        self,
        tool_name: str,
        arguments: Union[str, Dict[str, Any]],
        call_id: Optional[str] = None,
        confirmation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Intercept OpenAI function call before execution."""
        args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        action = self.translate_to_action(tool_name, args_dict)

        try:
            decision: InterceptionDecision = self.gate.evaluate_action(
                action=action,
                confirmation_token=confirmation_token,
            )
        except IrreversibleActionBlockedError as e:
            return {
                "tool_call_id": call_id or "call-001",
                "role": "tool",
                "name": tool_name,
                "content": json.dumps({
                    "error": "Execution blocked by SideGate Irreversible Action Gate",
                    "details": str(e),
                    "status": "BLOCKED",
                }),
                "decision": GatingDecisionType.BLOCKED.value,
                "blocked": True,
            }

        if decision.decision == GatingDecisionType.BLOCKED:
            return {
                "tool_call_id": call_id or "call-001",
                "role": "tool",
                "name": tool_name,
                "content": json.dumps({
                    "error": f"Blocked at {decision.layer.value} layer",
                    "reason": decision.reason,
                    "status": "BLOCKED",
                }),
                "decision": decision.decision.value,
                "blocked": True,
            }

        result = None
        if self.tool_dispatch_fn:
            result = self.tool_dispatch_fn(tool_name, args_dict)

        return {
            "tool_call_id": call_id or "call-001",
            "role": "tool",
            "name": tool_name,
            "content": json.dumps(result or {"status": "SUCCESS", "message": "Action permitted"}),
            "decision": decision.decision.value,
            "blocked": False,
        }

    def translate_to_action(self, tool_name: str, arguments: Dict[str, Any]) -> ActionPayload:
        """Map OpenAI tool call to ActionPayload."""
        name_lower = tool_name.lower()

        if any(w in name_lower for w in ["checkout", "pay", "order", "purchase", "wire", "transfer"]):
            return ActionPayload(
                category=ActionCategory.UI_CLICK,
                target=f"tool:{tool_name}",
                parameters=arguments,
            )
        elif any(w in name_lower for w in ["delete", "remove", "drop", "terminate"]):
            return ActionPayload(
                category=ActionCategory.FILE_DELETE if "file" in name_lower else ActionCategory.TOOL_INVOCATION,
                target=f"tool:{tool_name}",
                parameters=arguments,
            )
        elif any(w in name_lower for w in ["get", "read", "fetch", "list", "query"]):
            return ActionPayload(
                category=ActionCategory.HTTP_READ,
                target=f"tool:{tool_name}",
                parameters=arguments,
            )

        return ActionPayload(
            category=ActionCategory.TOOL_INVOCATION,
            target=f"tool:{tool_name}",
            parameters=arguments,
        )
