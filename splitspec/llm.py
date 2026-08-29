"""Model client layer (Module 4, minimal slice).

Module 4 only needs a thin way to call a model; the full agent tool loop, tool
schemas, and budgets belong to Module 5, which extends this module rather than
replacing it. The surface here is deliberately narrow:

- :class:`ModelClient` — the duck-type both agents and the contract builder use.
- :class:`Completion` — what a call returns.
- :class:`OpenAICompatibleClient` — one OpenAI-compatible POST per call, with
  round-robin key rotation on 429 and exponential-backoff retries.
- :class:`FakeClient` — scripted responses for tests; records what it was asked.

An API key never leaves the client: it is only placed in the request header and
is never logged, traced, or returned.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from splitspec.config import Provider


@dataclass
class Completion:
    """A single model completion."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass
class ToolCall:
    """A tool the model asked to run. ``arguments`` is a JSON string."""

    id: str
    name: str
    arguments: str


@dataclass
class ModelReply:
    """A single model completion within a tool loop.

    ``text`` is the assistant message and ``tool_calls`` any tools it requested;
    both may be empty together (a reasoning model that spent its whole budget and
    returned HTTP 200 with no content at all).
    """

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""  # "stop" | "length" | "tool_calls" | ...
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    # The provider's assistant message, verbatim. Replay this rather than rebuilding
    # one: Gemini 3.x rejects a reconstructed function call that dropped its
    # `thought_signature`, and other providers may attach fields we do not model.
    raw_message: dict[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        """True when the reply contributes nothing to steer the loop."""
        return not self.text and not self.tool_calls


class ModelClient(Protocol):
    """What anything that makes a model call depends on."""

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> Completion: ...

    def respond(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1000,
    ) -> ModelReply: ...


# transport: (url, headers, payload_dict) -> (status_code, response_dict)
Transport = Callable[[str, dict[str, str], dict[str, Any]], tuple[int, dict[str, Any]]]

# Default retry policy mirrors config.Settings; explicit values win when provided.
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_RETRY_BASE_DELAY = 2
_HTTP_TIMEOUT_SEC = 120.0


def _error_message(body: Any) -> str:
    """The provider's own explanation. Without it, an HTTP code alone sends you
    guessing at model ids, token ceilings, and payload limits.

    Gemini returns a JSON *list* wrapping the error object, OpenAI-compatible
    providers return a dict; accept either rather than failing while reporting a
    failure."""
    if isinstance(body, list) and body:
        body = body[0]
    if not isinstance(body, dict):
        return str(body)[:500]
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)[:500]
    if isinstance(error, list) and error:
        first = error[0]
        if isinstance(first, dict) and isinstance(first.get("error"), dict):
            return str(first["error"].get("message") or first)[:500]
        return str(first)[:500]
    return str(body)[:500]


def _http_post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Real transport: one blocking POST, returns (status, parsed json).

    httpx rather than urllib: urllib trusts only the interpreter's default CA
    location, which is empty in a venv on some distributions and fails every
    provider with CERTIFICATE_VERIFY_FAILED. httpx is already a dependency and
    uses certifi's bundle.
    """
    response = httpx.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", **headers},
        timeout=_HTTP_TIMEOUT_SEC,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"error": {"message": response.text[:2000]}}
    return response.status_code, body


class OpenAICompatibleClient:
    """One OpenAI-compatible chat-completions endpoint pinned to one model.

    ``api_keys`` holds several keys for the SAME model. On an HTTP 429 the next
    key is tried (round-robin) and the request is retried with exponential
    backoff; rotating models would change the experiment, rotating keys only
    changes throughput. ``transport`` is injectable so tests can exercise the
    retry/rotation logic without any network.
    """

    def __init__(
        self,
        provider: Provider,
        *,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay_sec: int = _DEFAULT_RETRY_BASE_DELAY,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._max_retries = max_retries
        self._retry_base_delay_sec = retry_base_delay_sec
        self._transport = transport or _http_post
        self._sleep = sleep
        self._key_index = 0

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> Completion:
        url = f"{self._provider.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._provider.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
        }

        attempts = self._max_retries + 1
        for attempt in range(attempts):
            if attempt > 0:
                self._sleep(self._retry_base_delay_sec * (2 ** (attempt - 1)))

            key = self._key(self._key_index)
            headers = {"Authorization": f"Bearer {key}"}
            status, body = self._transport(url, headers, payload)

            if status == 429:
                # Prefer another key for this same model; with only one key there is
                # nothing to rotate to, so fall through to the backoff at the top of
                # the next attempt. Raising here would abandon a sweep the moment a
                # free-tier limit is touched, which is the normal case, not an error.
                if self._key_index + 1 < len(self._provider.api_keys):
                    self._key_index += 1
                continue
            if not (200 <= status < 300):
                raise RuntimeError(
                    f"model API returned HTTP {status} for model {self._provider.model!r}: "
                    f"{_error_message(body)}"
                )
            return self._parse(body)

        raise RuntimeError(f"model API kept returning HTTP 429 for {self._provider.model!r}")

    def respond(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1000,
    ) -> ModelReply:
        """Tool-capable call, same retry/rotation policy as :meth:`complete`.

        ``tools`` is an OpenAI-style function list; an empty list is treated the
        same as no tools so a loop can pass its current tool set regardless.
        """
        url = f"{self._provider.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._provider.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        # 429 is handled by this client (key rotation then backoff); the caller
        # must not wrap respond() in its own retry layer on top of that.
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            if attempt > 0:
                self._sleep(self._retry_base_delay_sec * (2 ** (attempt - 1)))

            key = self._key(self._key_index)
            headers = {"Authorization": f"Bearer {key}"}
            status, body = self._transport(url, headers, payload)

            if status == 429:
                if self._key_index + 1 < len(self._provider.api_keys):
                    self._key_index += 1
                continue
            if not (200 <= status < 300):
                raise RuntimeError(
                    f"model API returned HTTP {status} for model {self._provider.model!r}: "
                    f"{_error_message(body)}"
                )
            return self._parse_reply(body)

        raise RuntimeError(f"model API kept returning HTTP 429 for {self._provider.model!r}")

    def _key(self, index: int) -> str:
        keys = self._provider.api_keys
        return keys[index % len(keys)]

    @staticmethod
    def _parse(body: dict[str, Any]) -> Completion:
        choice = body["choices"][0]["message"]
        usage = body.get("usage") or {}
        return Completion(
            text=choice.get("content", "") or "",
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            model=body.get("model", ""),
        )

    @staticmethod
    def _parse_reply(body: dict[str, Any]) -> ModelReply:
        choice = body["choices"][0]
        msg = choice.get("message") or {}
        usage = body.get("usage") or {}

        tool_calls: list[ToolCall] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=raw.get("id", "") or "",
                    name=fn.get("name", "") or "",
                    arguments=fn.get("arguments", "") or "",
                )
            )

        return ModelReply(
            text=msg.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "") or "",
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            model=body.get("model", ""),
            raw_message=dict(msg),
        )


class FakeClient:
    """Scripted :class:`ModelClient` for tests. Returns queued responses and
    records every request it was asked to fulfil.

    ``responses`` feeds :meth:`complete` (used by the contract builder) and
    ``replies`` feeds :meth:`respond` (used by the tool loop) independently, so a
    test driving either never interferes with the other.
    """

    def __init__(
        self,
        responses: list[Completion] | None = None,
        replies: list[ModelReply] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []
        self.respond_calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> Completion:
        self.calls.append(
            {"system": system, "messages": messages, "max_tokens": max_tokens}
        )
        if not self._responses:
            raise RuntimeError("FakeClient ran out of scripted responses")
        return self._responses.pop(0)

    def respond(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1000,
    ) -> ModelReply:
        self.respond_calls.append(
            {
                "system": system,
                "messages": messages,
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        if not self._replies:
            raise RuntimeError("FakeClient ran out of scripted replies")
        return self._replies.pop(0)
