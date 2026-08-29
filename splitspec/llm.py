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

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import request

from splitspec.config import Provider


@dataclass
class Completion:
    """A single model completion."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class ModelClient(Protocol):
    """What anything that makes a model call depends on."""

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> Completion: ...


# transport: (url, headers, payload_dict) -> (status_code, response_dict)
Transport = Callable[[str, dict[str, str], dict[str, Any]], tuple[int, dict[str, Any]]]

# Default retry policy mirrors config.Settings; explicit values win when provided.
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_RETRY_BASE_DELAY = 2


def _http_post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Real transport: one blocking POST, returns (status, parsed json)."""
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)


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

            if status == 429 and self._key_index + 1 < len(self._provider.api_keys):
                # Try the next key before backing off any further.
                self._key_index += 1
                continue
            if not (200 <= status < 300):
                raise RuntimeError(
                    f"model API returned HTTP {status} for model {self._provider.model!r}"
                )
            return self._parse(body)

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


class FakeClient:
    """Scripted :class:`ModelClient` for tests. Returns queued responses and
    records every request it was asked to fulfil."""

    def __init__(self, responses: list[Completion]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

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
