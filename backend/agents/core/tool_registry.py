"""Tool Registry — centralized tool registration with fallback support.

Every tool agent can use is registered here.  Agents call:
    registry.get_specs()   → OpenAI-compatible tool definitions
    registry.execute(...)  → run a tool with automatic fallback

Adding a new tool is ONE step: `registry.register(Tool(...))`.
No more if/else chains spread across agent code.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """A registered tool with optional fallback."""
    name: str
    description: str
    parameters: dict          # JSON Schema for OpenAI function calling
    handler: Callable         # (args: dict, user_id: int | None) -> str
    fallback: Optional[Callable] = None  # alternate handler if primary fails


class ToolRegistry:
    """Thread-safe registry of all available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool.  Overwrites if name already exists."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_specs(self) -> list[dict]:
        """Return OpenAI-compatible tool definitions for all registered tools."""
        return [{
            'type': 'function',
            'function': {
                'name': t.name,
                'description': t.description,
                'parameters': t.parameters,
            },
        } for t in self._tools.values()]

    def execute(self, name: str, args: dict,
                user_id: Optional[int] = None) -> str:
        """Execute a tool by name.  Falls back if primary fails.

        Returns the tool's output as a string, or an error message.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"未知工具: {name}"

        # Try primary handler
        try:
            return tool.handler(args, user_id)
        except Exception as exc:
            logger.warning("Tool '%s' failed: %s", name, exc)

            # Try fallback
            if tool.fallback:
                try:
                    logger.info("Tool '%s': using fallback", name)
                    return tool.fallback(args, user_id)
                except Exception as fb_exc:
                    logger.warning("Tool '%s' fallback also failed: %s", name, fb_exc)

            return f"工具 {name} 执行失败: {exc}"

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())


# ── Global singleton ────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_tool_registry() -> None:
    """Reset the singleton (for tests)."""
    global _registry
    _registry = None
