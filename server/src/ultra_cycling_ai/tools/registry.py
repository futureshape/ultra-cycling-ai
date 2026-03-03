"""Tool base class and registry for OpenAI function-calling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for all agent tools."""

    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's input

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict:
        """Run the tool and return a result dict."""
        ...

    def openai_function_schema(self) -> dict:
        """Return the schema in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Holds all registered tools and dispatches calls."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def dispatch(self, name: str, kwargs: dict) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        return await tool.execute(**kwargs)

    def openai_tool_definitions(self) -> list[dict]:
        """Return a list of tool schemas suitable for the OpenAI API."""
        return [t.openai_function_schema() for t in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


def build_default_registry() -> ToolRegistry:
    """Create and return a registry with all built-in tools."""
    from ultra_cycling_ai.tools.route_analysis import RouteAnalysisTool
    # from ultra_cycling_ai.tools.poi_search import POISearchTool
    from ultra_cycling_ai.tools.weather import WeatherForecastTool
    from ultra_cycling_ai.tools.daylight import DaylightTool

    registry = ToolRegistry()
    registry.register(RouteAnalysisTool())
    # registry.register(POISearchTool())
    registry.register(WeatherForecastTool())
    registry.register(DaylightTool())
    return registry
