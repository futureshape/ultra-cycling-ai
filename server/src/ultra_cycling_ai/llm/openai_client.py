"""Async OpenAI chat-completion wrapper with function-calling support."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ultra_cycling_ai.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=90.0,  # seconds — LLM calls with tool loops can be slow
            max_retries=0,  # we handle retries ourselves
        )
    return _client


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    id: str
    function_name: str
    function_args: dict[str, Any]


@dataclass
class LLMResponse:
    """Simplified wrapper around an OpenAI chat completion response."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_message(self) -> dict:
        """Convert back to an assistant message dict (for multi-turn tool loops)."""
        msg: dict[str, Any] = {"role": "assistant"}
        if self.text:
            msg["content"] = self.text
        if self.tool_calls:
            msg["content"] = None
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function_name,
                        "arguments": json.dumps(tc.function_args),
                    },
                }
                for tc in self.tool_calls
            ]
        return msg


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

MAX_RETRIES = 3


async def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
) -> LLMResponse:
    """Send a chat completion request to OpenAI and return a parsed LLMResponse.

    Retries up to MAX_RETRIES times on transient errors.
    """
    client = _get_client()
    model = model or settings.openai_model

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    msg_count = len(messages)
    logger.debug(
        "[llm] Request: model=%s messages=%d tools=%d",
        model, msg_count, len(tools) if tools else 0,
    )

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(**kwargs)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("OpenAI call attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                import asyncio

                await asyncio.sleep(2**attempt)
    else:
        raise RuntimeError(f"OpenAI call failed after {MAX_RETRIES} retries") from last_err

    choice = resp.choices[0]
    usage = resp.usage
    logger.debug(
        "[llm] Response: finish_reason=%s tokens(prompt=%s completion=%s total=%s)",
        choice.finish_reason,
        usage.prompt_tokens if usage else "?",
        usage.completion_tokens if usage else "?",
        usage.total_tokens if usage else "?",
    )

    # Parse tool calls if present.
    tool_calls: list[ToolCall] = []
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    function_name=tc.function.name,
                    function_args=args,
                )
            )

    result = LLMResponse(
        text=choice.message.content or "",
        tool_calls=tool_calls,
    )

    if result.tool_calls:
        logger.debug(
            "[llm] Tool calls: %s",
            [(tc.function_name, tc.function_args) for tc in result.tool_calls],
        )
    elif result.text:
        logger.debug("[llm] Content: %s", result.text[:500])

    return result
