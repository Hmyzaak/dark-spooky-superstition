"""Provider-neutrální datové struktury pro komunikaci s jazykovým modelem."""

from dataclasses import dataclass, field
from typing import Any, Literal


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    """Jedno volání nástroje požadované jazykovým modelem."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """Zpráva v interním konverzačním formátu agenta."""

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolDefinition:
    """Popis nástroje nezávislý na konkrétním LLM poskytovateli."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class LLMRequest:
    """Kompletní požadavek předávaný adaptéru jazykového modelu."""

    messages: list[ChatMessage]
    tools: list[ToolDefinition] = field(default_factory=list)


@dataclass
class LLMResponse:
    """Normalizovaná odpověď jazykového modelu."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
