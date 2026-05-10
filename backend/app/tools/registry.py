"""Tools the agent can call. Each tool is:

    @register
    async def my_tool(client: FhirClient, **kwargs) -> dict | list:
        ...

and exposes a `_schema` attribute used to build the OpenAI tool spec.
"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.fhir import FhirClient

ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable[[ToolFn], ToolFn]:
    """Register a tool. The function's first arg must be `client: FhirClient`."""

    def decorator(fn: ToolFn) -> ToolFn:
        sig = inspect.signature(fn)
        first = next(iter(sig.parameters))
        if first != "client":
            raise TypeError(f"tool {name}: first parameter must be 'client'")
        _REGISTRY[name] = Tool(
            name=name, description=description, parameters=parameters, fn=fn
        )
        return fn

    return decorator


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


async def execute(name: str, args: dict[str, Any], client: FhirClient) -> Any:
    t = _REGISTRY.get(name)
    if t is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await t.fn(client, **args)
    except Exception as e:  # noqa: BLE001 — tool errors must not crash the agent
        return {"error": f"{type(e).__name__}: {e}"}
