"""Typed tool registry with hosted-vs-local routing.

Agents request a tool by ``tool_id``. The registry returns the first available
implementation in order: hosted client (preferred) -> local binary wrapper ->
raises :class:`ToolUnavailable`.

This is the seam that makes ecosystem and target-pack swaps tractable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Tool, ToolUnavailable
from .megahit import MegahitTool

BUILTIN_TOOL_MAPPINGS: dict[str, Tool] = {
    "assembly.megahit": MegahitTool(),
}


@dataclass
class ToolEntry:
    tool_id: str
    implementations: list[Tool] = field(default_factory=list)  # in preference order

    def best_available(self) -> Tool:
        for impl in self.implementations:
            if impl.is_available():
                return impl
        raise ToolUnavailable(
            f"No available implementation for tool '{self.tool_id}'. "
            f"Tried: {[type(i).__name__ for i in self.implementations]}"
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ToolEntry] = {}

    def register(self, tool: Tool, *, prepend: bool = False) -> None:
        entry = self._entries.setdefault(tool.tool_id, ToolEntry(tool_id=tool.tool_id))
        if prepend:
            entry.implementations.insert(0, tool)
        else:
            entry.implementations.append(tool)

    def get(self, tool_id: str) -> Tool:
        if tool_id not in self._entries:
            raise ToolUnavailable(f"Unknown tool '{tool_id}'")
        return self._entries[tool_id].best_available()

    def has_available(self, tool_id: str) -> bool:
        if tool_id not in self._entries:
            return False
        try:
            self._entries[tool_id].best_available()
            return True
        except ToolUnavailable:
            return False

    def known_ids(self) -> list[str]:
        return sorted(self._entries.keys())

    def availability_report(self) -> dict[str, bool]:
        return {tid: self.has_available(tid) for tid in self.known_ids()}
