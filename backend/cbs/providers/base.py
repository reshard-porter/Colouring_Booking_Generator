"""Image-provider interface. Providers are optional; the core app never needs one."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class GeneratedImage:
    data: bytes
    mime: str
    usage: dict = field(default_factory=dict)
    revised_prompt: str | None = None
    provider_request_id: str | None = None


class ProviderRequestFailed(Exception):
    """The provider definitely did NOT accept the request (e.g. validation error, auth error,
    connection refused before sending). Safe to retry manually."""


class ProviderOutcomeUnknown(Exception):
    """The request may have been accepted (timeout after sending, dropped connection, 5xx).
    Never retry automatically: it could create a duplicate charge."""
    outcome_unknown = True


class ImageProvider(Protocol):
    name: str

    def status(self) -> dict: ...
    def capabilities(self) -> dict: ...
    def generate(self, prompt: str, *, size: str, quality: str | None, references: list[bytes] | None) -> GeneratedImage: ...
