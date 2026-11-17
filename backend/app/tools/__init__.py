"""Tool registry — importing this module side-effect-registers all tools."""
from app.tools import chw as _chw  # noqa: F401  (registers CHW tools)
from app.tools import clinical as _clinical  # noqa: F401  (registers clinical tools)
from app.tools import patient as _patient  # noqa: F401  (registers patient tools)
from app.tools import quality as _quality  # noqa: F401  (registers data-quality tools)
from app.tools.registry import (
    Tool,
    all_tools,
    execute,
    get_tool,
    tool,
)

__all__ = ["Tool", "all_tools", "execute", "get_tool", "tool"]
