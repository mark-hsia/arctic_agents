from hyphae.tools import ToolRegistry, ToolUnavailable
from hyphae.tools.base import Tool, ToolRunResult


class _Always(Tool):
    tool_id = "x.always"
    binary = None

    def run(self, **kwargs):  # type: ignore[no-untyped-def]
        return ToolRunResult(tool_id=self.tool_id)


class _Never(Tool):
    tool_id = "x.never"
    binary = "definitely-not-installed-xyz"

    def run(self, **kwargs):  # type: ignore[no-untyped-def]
        return ToolRunResult(tool_id=self.tool_id)


def test_registry_returns_first_available() -> None:
    reg = ToolRegistry()
    reg.register(_Never())
    reg.register(_Always())
    # Both register under different ids; pick by id.
    assert reg.has_available("x.always") is True
    assert reg.has_available("x.never") is False
    try:
        reg.get("x.never")
    except ToolUnavailable:
        return
    raise AssertionError("expected ToolUnavailable")


def test_prepend_changes_preference_order() -> None:
    reg = ToolRegistry()

    class A(Tool):
        tool_id = "y"
        binary = None

        def run(self, **kwargs):  # type: ignore[no-untyped-def]
            return ToolRunResult(tool_id="A")

    class B(Tool):
        tool_id = "y"
        binary = None

        def run(self, **kwargs):  # type: ignore[no-untyped-def]
            return ToolRunResult(tool_id="B")

    reg.register(A())
    reg.register(B(), prepend=True)
    chosen = reg.get("y")
    assert chosen.run().tool_id == "B"


def test_unknown_tool_raises() -> None:
    reg = ToolRegistry()
    try:
        reg.get("missing")
    except ToolUnavailable:
        return
    raise AssertionError
