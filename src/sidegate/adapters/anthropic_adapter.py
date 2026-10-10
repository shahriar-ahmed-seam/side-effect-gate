"""Adapter intercepting Anthropic Computer Use and Bash tool execution."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from sidegate.core.exceptions import IrreversibleActionBlockedError
from sidegate.core.models import (
    ActionCategory,
    ActionPayload,
    ActionTier,
    GatingDecisionType,
)
from sidegate.gating.gate import RuntimeActionGate


class AnthropicComputerUseAdapter:
    """Interception wrapper for Anthropic Claude Computer Use tool calls."""

    def __init__(
        self,
        gate: Optional[RuntimeActionGate] = None,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> None:
        self.gate = gate or RuntimeActionGate()
        self.tool_executor = tool_executor

    def intercept_and_execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_use_id: Optional[str] = None,
        confirmation_token: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Intercept Anthropic tool call before execution."""
        action = self.translate_to_action(tool_name, tool_input)

        try:
            decision = self.gate.evaluate_action(
                action=action,
                confirmation_token=confirmation_token,
                context=context,
            )
        except IrreversibleActionBlockedError as e:
            return {
                "tool_use_id": tool_use_id or "tool-call",
                "is_error": True,
                "content": f"[SideGate Interception]: {str(e)}",
                "decision": GatingDecisionType.BLOCKED.value,
                "blocked": True,
            }

        if decision.decision == GatingDecisionType.BLOCKED:
            return {
                "tool_use_id": tool_use_id or "tool-call",
                "is_error": True,
                "content": f"[SideGate Interception]: Action blocked at {decision.layer.value} layer ({decision.reason})",
                "decision": decision.decision.value,
                "blocked": True,
            }

        # Action is permitted or monitored
        output = None
        if self.tool_executor:
            output = self.tool_executor(tool_name, tool_input)

        return {
            "tool_use_id": tool_use_id or "tool-call",
            "is_error": False,
            "content": output or "Action executed successfully under SideGate monitoring",
            "decision": decision.decision.value,
            "blocked": False,
        }

    def translate_to_action(self, tool_name: str, tool_input: Dict[str, Any]) -> ActionPayload:
        """Translate Anthropic Computer Use tool payload into standardized ActionPayload."""
        if tool_name == "bash":
            cmd = str(tool_input.get("command", "")).strip()
            return ActionPayload(
                category=ActionCategory.SHELL_COMMAND,
                target=cmd,
                parameters={"command": cmd},
            )

        if tool_name == "computer":
            action_type = str(tool_input.get("action", "")).lower()
            coord = tool_input.get("coordinate", [])
            text = str(tool_input.get("text", ""))

            if action_type in ("left_click", "right_click", "double_click", "mouse_click"):
                target_str = f"coordinate:({coord[0]},{coord[1]})" if len(coord) == 2 else "mouse_click"
                return ActionPayload(
                    category=ActionCategory.UI_CLICK,
                    target=target_str,
                    parameters={"coordinate": coord, "text": text},
                )
            elif action_type in ("type", "key"):
                return ActionPayload(
                    category=ActionCategory.UI_KEYSTROKE,
                    target="input_field",
                    parameters={"text": text},
                )
            elif action_type in ("screenshot", "cursor_position"):
                return ActionPayload(
                    category=ActionCategory.UI_NAVIGATION,
                    target=action_type,
                    tier=ActionTier.TIER_0_READ_ONLY,
                )

        return ActionPayload(
            category=ActionCategory.TOOL_INVOCATION,
            target=tool_name,
            parameters=tool_input,
        )
