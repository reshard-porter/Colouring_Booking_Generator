"""OpenAI text adapter for story pages (optional; uses the same API key as image generation).

Checked against OpenAI's docs on 2026-11-03 (https://developers.openai.com/api/docs/guides/text):
- POST /v1/responses with {model, instructions, input, max_output_tokens}; the Responses API is recommended for new
  text-generation work. The reply's text is in output[] items of type "message" whose content has type "output_text"
  (it is not safe to assume it is at output[0]); the SDK's `output_text` field is a convenience the raw JSON may lack.
- Current models: the GPT-5.6 family – gpt-5.6-sol (flagship), gpt-5.6-terra (balance of quality and cost),
  gpt-5.6-luna (cost-sensitive) – and gpt-5.5. Model availability depends on the account; "Test connection" checks.

Prices are NOT built in: cost is estimated only from a per-story figure the owner enters.
"""
from __future__ import annotations

import time

import httpx

from .base import ProviderOutcomeUnknown, ProviderRequestFailed
from .openai_images import API_BASE, friendly_error

DOCS_URL = "https://developers.openai.com/api/docs/guides/text"
DEFAULT_TEXT_MODEL = "gpt-5.6-terra"
TEXT_MODEL_CHOICES = [
    {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra – good writing at a moderate price (recommended)"},
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna – cheapest"},
    {"id": "gpt-5.6-sol", "label": "GPT-5.6 Sol – most capable, most expensive"},
    {"id": "gpt-5.5", "label": "GPT-5.5"},
]


def extract_text(body: dict) -> str:
    if isinstance(body.get("output_text"), str) and body["output_text"].strip():
        return body["output_text"].strip()
    parts = []
    for item in body.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and c.get("text"):
                    parts.append(c["text"])
    return "\n".join(parts).strip()


class OpenAITextProvider:
    name = "openai"

    def __init__(self, api_key: str | None, model: str = DEFAULT_TEXT_MODEL, timeout: float = 180.0, base_url: str = API_BASE,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.api_key = (api_key or "").strip() or None
        self.model = (model or DEFAULT_TEXT_MODEL).strip()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.sleep = sleep

    def status(self) -> dict:
        return {"provider": self.name, "configured": bool(self.api_key), "model": self.model, "live": True, "docs": DOCS_URL,
                "note": None if self.api_key else "Add an OpenAI API key to write story text with AI."}

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=httpx.Timeout(self.timeout, connect=20.0), transport=self.transport,
                            headers={"Authorization": f"Bearer {self.api_key}"})

    def test_connection(self) -> dict:
        if not self.api_key:
            return {"ok": False, "message": "No API key saved."}
        try:
            with self._client() as c:
                r = c.get(f"{self.base_url}/models/{self.model}")
        except httpx.HTTPError as e:
            return {"ok": False, "message": f"Could not reach api.openai.com ({type(e).__name__})."}
        if r.status_code == 200:
            return {"ok": True, "message": f"Connected. Your key can use {self.model} for story text."}
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = r.text[:200]
        return {"ok": False, "message": friendly_error(r.status_code, msg, self.model)}

    def write(self, instructions: str, prompt: str, max_output_tokens: int = 4000) -> dict:
        if not self.api_key:
            raise ProviderRequestFailed("No OpenAI API key saved.")
        payload = {"model": self.model, "instructions": instructions, "input": prompt, "max_output_tokens": max_output_tokens,
                   "reasoning": {"effort": "low"}}
        for attempt in range(4):
            try:
                with self._client() as c:
                    r = c.post(f"{self.base_url}/responses", json=payload)
            except httpx.ConnectError as e:  # never sent – safe to retry
                if attempt < 3:
                    self.sleep(3 * (attempt + 1))
                    continue
                raise ProviderRequestFailed(f"Could not reach api.openai.com ({type(e).__name__}).") from e
            except httpx.TimeoutException as e:  # may have been processed and billed – don't retry blindly
                raise ProviderOutcomeUnknown("OpenAI didn't answer in time; the request may still have been billed.") from e
            if r.status_code == 200:
                body = r.json()
                text = extract_text(body)
                if not text:
                    raise ProviderRequestFailed("OpenAI returned no text" + (f" (status: {body.get('status')})" if body.get("status") else "") + ".")
                return {"text": text, "usage": body.get("usage"), "request_id": r.headers.get("x-request-id"), "model": body.get("model", self.model)}
            try:
                msg = r.json().get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                msg = r.text[:200]
            if r.status_code == 400 and "reasoning" in msg.lower() and "reasoning" in payload:
                payload.pop("reasoning")  # model doesn't take a reasoning setting – ask again without it
                continue
            if r.status_code == 429 and attempt < 3 and not any(w in msg.lower() for w in ("quota", "billing", "insufficient")):
                self.sleep(min(float(r.headers.get("retry-after", 0) or 0) or 10 * (attempt + 1), 60))
                continue
            raise ProviderRequestFailed(friendly_error(r.status_code, msg, self.model))
        raise ProviderRequestFailed("OpenAI kept refusing the request; try again later.")


class MockTextProvider:
    """TEST-ONLY: deterministic placeholder text, always labelled as a mock."""
    name = "mock"

    def __init__(self, words: int = 420):
        self.words = words
        self.calls = 0
        self.last = None

    def status(self) -> dict:
        return {"provider": self.name, "configured": True, "model": "mock-text-model", "live": False}

    def test_connection(self) -> dict:
        return {"ok": True, "message": "Mock text provider."}

    def write(self, instructions: str, prompt: str, max_output_tokens: int = 4000) -> dict:
        self.calls += 1
        self.last = {"instructions": instructions, "prompt": prompt}
        sentence = "MOCK story sentence about the picture on the right for automated tests only"
        words = []
        while len(words) < self.words:
            words += sentence.split() + ["."]
        body = " ".join(words[: self.words]).replace(" .", ".")
        half = len(body) // 2
        cut = body.find(". ", half) + 1 or half
        return {"text": body[:cut].strip() + "\n\n" + body[cut:].strip(), "usage": {"output_tokens": self.words}, "request_id": None,
                "model": "mock-text-model"}
