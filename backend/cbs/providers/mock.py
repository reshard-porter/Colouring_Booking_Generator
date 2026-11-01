"""TEST-ONLY mock provider. Enabled only when CBS_ENABLE_MOCK_PROVIDER=1 and always labelled as a mock,
so it can never masquerade as live generation."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from .base import GeneratedImage, ProviderOutcomeUnknown, ProviderRequestFailed


class MockProvider:
    name = "mock"

    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior
        self.calls = 0

    def status(self) -> dict:
        return {"provider": self.name, "configured": True, "model": "mock-test-model", "live": False,
                "note": "MOCK PROVIDER FOR AUTOMATED TESTS – images are placeholders, not AI output."}

    def capabilities(self) -> dict:
        return {"generate": True, "reference_images": True, "seed": False, "sizes": ["1024x1536"],
                "size_presets": [{"id": "1024x1536", "label": "Mock 1024×1536", "flex": False}], "quality": ["high"],
                "models": [{"id": "mock-test-model", "label": "Mock (tests only)"}]}

    def generate(self, prompt, *, size="1024x1536", quality=None, references=None) -> GeneratedImage:
        self.calls += 1
        self.last = {"prompt": prompt, "size": size, "quality": quality, "references": len(references or [])}
        if self.behavior == "fail":
            raise ProviderRequestFailed("mock rejection")
        if self.behavior == "unknown":
            raise ProviderOutcomeUnknown("mock timeout after send")
        w, h = (int(x) for x in size.split("x"))
        im = Image.new("L", (w, h), 255)
        d = ImageDraw.Draw(im)
        d.ellipse([w * 0.2, h * 0.3, w * 0.8, h * 0.7], outline=0, width=12)
        d.rectangle([w * 0.3, h * 0.72, w * 0.7, h * 0.85], outline=0, width=12)
        d.text((20, 20), "MOCK", fill=0)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return GeneratedImage(buf.getvalue(), "image/png", usage={"mock": True})
