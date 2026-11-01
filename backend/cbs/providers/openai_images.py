"""OpenAI Images API adapter (optional, disabled until an API key is configured).

Checked against OpenAI's official API reference on 2026-10-30
(https://developers.openai.com/api/reference/resources/images):
- POST /v1/images/generations (JSON) and POST /v1/images/edits (JSON with an `images` array of
  {image_url | file_id}); GPT image models always return base64 (`data[].b64_json`).
- gpt-image-1 was shut down on 2026-10-23. Current models: gpt-image-2.5-sunburst (quality-first),
  gpt-image-2.5-flare (speed-first), gpt-image-2; plus gpt-image-1.5 / gpt-image-1-mini (fixed sizes).
- gpt-image-2 / 2.5 accept custom WIDTHxHEIGHT: edges multiples of 16, each edge ≤ 3840, ratio ≤ 3:1,
  total pixels 655,360–8,294,400; above 3,686,400 pixels OpenAI marks output "experimental".
- quality low/medium/high (+ xhigh/max on 2.5 models); background opaque supported.
- Image models may require OpenAI organization verification (403 otherwise).

Prices are NOT built in: costs are estimated only from a per-image figure the owner enters.
"""
from __future__ import annotations

import base64
import time

import httpx

from .base import GeneratedImage, ProviderOutcomeUnknown, ProviderRequestFailed

API_BASE = "https://api.openai.com/v1"
DOCS_URL = "https://developers.openai.com/api/reference/resources/images"
DEFAULT_MODEL = "gpt-image-2.5-sunburst"

FLEX_MODELS = {"gpt-image-2", "gpt-image-2-2026-04-21", "gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2026-09-08",
               "gpt-image-2.5-flare", "gpt-image-2.5-flare-2026-09-08"}
FIXED_MODELS = {"gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest"}
RETIRED = {"gpt-image-1": "gpt-image-1 was shut down by OpenAI on 2026-10-23", "dall-e-2": "retired 2026-05-12",
           "dall-e-3": "retired 2026-05-12"}
MODEL_CHOICES = [
    {"id": "gpt-image-2.5-sunburst", "label": "GPT Image 2.5 Sunburst – best quality (recommended)"},
    {"id": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare – faster"},
    {"id": "gpt-image-2", "label": "GPT Image 2"},
    {"id": "gpt-image-1.5", "label": "GPT Image 1.5 – fixed sizes only (lower resolution)"},
    {"id": "gpt-image-1-mini", "label": "GPT Image 1 mini – cheapest, fixed sizes, drafts"},
]
# Portrait 3:4 matches the 7.5 × 10 in safe area of an 8.5 × 11 page.
SIZE_PRESETS = [
    {"id": "2400x3200", "label": "Print – 2400×3200 (≈320 DPI full page; OpenAI marks >3.7 MP experimental)", "flex": True},
    {"id": "1632x2176", "label": "Standard – 1632×2176 (≈218 DPI full page)", "flex": True},
    {"id": "1024x1536", "label": "Basic – 1024×1536 (≈154 DPI full page)", "flex": False},
]
MAX_PIXELS, EXPERIMENTAL_PIXELS, MIN_PIXELS = 8_294_400, 3_686_400, 655_360


def validate_size(model: str, size: str) -> str | None:
    """Return an error message, or None if the size is allowed for the model."""
    if size in ("1024x1024", "1024x1536", "1536x1024", "auto"):
        return None
    if model not in FLEX_MODELS:
        return f"{model} only supports 1024x1024, 1024x1536 and 1536x1024."
    try:
        w, h = (int(v) for v in size.lower().split("x"))
    except ValueError:
        return "Size must look like WIDTHxHEIGHT."
    if w % 16 or h % 16:
        return "Width and height must be multiples of 16."
    if max(w, h) > 3840:
        return "Each edge must be at most 3840 pixels."
    if max(w, h) / min(w, h) > 3:
        return "Aspect ratio must be between 1:3 and 3:1."
    if not MIN_PIXELS <= w * h <= MAX_PIXELS:
        return "Total pixels must be between 655,360 and 8,294,400."
    return None


def friendly_error(status: int, msg: str, model: str) -> str:
    low = (msg or "").lower()
    if status == 401:
        return "OpenAI rejected the API key (401). Check that you pasted the whole key and that it hasn't been revoked."
    if status == 403 and "verif" in low:
        return ("OpenAI says your organization must be verified to use this image model (403). Verify it at "
                "https://platform.openai.com/settings/organization/general – access can take ~15 minutes to appear.")
    if status == 403:
        return f"OpenAI refused access to {model} (403): {msg}"
    if status == 404:
        return f"Model “{model}” isn't available to this API key (404). Pick another model in Settings."
    if status == 429 and ("quota" in low or "billing" in low or "insufficient" in low):
        return "Your OpenAI account has no remaining credit or quota (429). Add credit at https://platform.openai.com/settings/organization/billing."
    if status == 429:
        return "OpenAI rate limit reached (429). Try again in a minute."
    if status == 400 and ("safety" in low or "moderation" in low or "policy" in low):
        return f"OpenAI's safety system rejected this prompt (400): {msg}"
    return f"OpenAI rejected the request ({status}): {msg}"


class OpenAIImagesProvider:
    name = "openai"

    def __init__(self, api_key: str | None, model: str = DEFAULT_MODEL, timeout: float = 360.0, base_url: str = API_BASE,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.api_key = (api_key or "").strip() or None
        self.model = (model or DEFAULT_MODEL).strip()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.sleep = sleep

    def status(self) -> dict:
        note = None
        if not self.api_key:
            note = "Add an OpenAI API key to enable generation."
        elif self.model in RETIRED:
            note = f"Model {self.model}: {RETIRED[self.model]}. Choose a current model in Settings."
        return {"provider": self.name, "configured": bool(self.api_key) and self.model not in RETIRED, "model": self.model,
                "docs": DOCS_URL, "live": True, "note": note}

    def capabilities(self) -> dict:
        flex = self.model in FLEX_MODELS
        return {
            "generate": True, "reference_images": True, "seed": False,
            "sizes": [s["id"] for s in SIZE_PRESETS if flex or not s["flex"]],
            "size_presets": [s for s in SIZE_PRESETS if flex or not s["flex"]],
            "quality": ["low", "medium", "high"] + (["xhigh", "max"] if self.model.startswith("gpt-image-2.5") else []),
            "models": MODEL_CHOICES,
            "resolution_note": ("Print size 2400×3200 gives about 320 DPI on a full 8.5×11 page. Smaller sizes print softer; "
                                "the app can smooth-enlarge line art, but that never adds real detail."),
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=httpx.Timeout(self.timeout, connect=20.0), transport=self.transport,
                            headers={"Authorization": f"Bearer {self.api_key}"})

    def test_connection(self) -> dict:
        """Free check: retrieves the model record (no image is generated, nothing is billed)."""
        if not self.api_key:
            return {"ok": False, "message": "No API key saved."}
        if self.model in RETIRED:
            return {"ok": False, "message": f"{self.model}: {RETIRED[self.model]}."}
        try:
            with self._client() as c:
                r = c.get(f"{self.base_url}/models/{self.model}")
        except httpx.HTTPError as e:
            return {"ok": False, "message": f"Could not reach api.openai.com ({type(e).__name__}). Check your internet connection."}
        if r.status_code == 200:
            return {"ok": True, "message": f"Connected. Your key can see {self.model}. (Image models may still need organization "
                                           "verification – the first sample page will confirm.)"}
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = r.text[:200]
        return {"ok": False, "message": friendly_error(r.status_code, msg, self.model)}

    def generate(self, prompt: str, *, size: str = "2400x3200", quality: str | None = "high",
                 references: list[bytes] | None = None) -> GeneratedImage:
        if not self.api_key:
            raise ProviderRequestFailed("No API key configured.")
        if self.model in RETIRED:
            raise ProviderRequestFailed(f"{self.model}: {RETIRED[self.model]}.")
        err = validate_size(self.model, size)
        if err:
            raise ProviderRequestFailed(err)
        body = {"model": self.model, "prompt": prompt, "size": size, "n": 1, "output_format": "png", "background": "opaque"}
        if quality:
            body["quality"] = quality
        if references:
            body["images"] = [{"image_url": "data:image/png;base64," + base64.b64encode(d).decode()} for d in references[:16]]
            url = f"{self.base_url}/images/edits"
        else:
            url = f"{self.base_url}/images/generations"
        # Only DEFINITE rejections (connection refused, 429 rate limit) are retried – never timeouts after sending.
        for attempt in range(4):
            try:
                with self._client() as c:
                    r = c.post(url, json=body)
            except httpx.ConnectError as e:
                if attempt < 3:
                    self.sleep(3 * (attempt + 1))
                    continue
                raise ProviderRequestFailed(f"Could not connect to OpenAI: {e}") from e
            except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError) as e:
                raise ProviderOutcomeUnknown(f"The request was sent but no complete response arrived ({type(e).__name__}). "
                                             "It may still have been processed and billed – check your OpenAI usage page.") from e
            if r.status_code == 429 and attempt < 3:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001
                    msg = ""
                if "quota" in msg.lower() or "billing" in msg.lower():
                    raise ProviderRequestFailed(friendly_error(429, msg, self.model))
                wait = float(r.headers.get("retry-after", 0) or 0) or 10 * (attempt + 1)
                self.sleep(min(wait, 60))
                continue
            break
        req_id = r.headers.get("x-request-id")
        if r.status_code >= 500:
            raise ProviderOutcomeUnknown(f"OpenAI server error {r.status_code} (request id {req_id}). Outcome unknown – check your usage page.")
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text[:300])
            except Exception:  # noqa: BLE001
                msg = r.text[:300]
            raise ProviderRequestFailed(friendly_error(r.status_code, msg, self.model))
        try:
            j = r.json()
            data = base64.b64decode(j["data"][0]["b64_json"])
        except Exception as e:  # noqa: BLE001
            raise ProviderOutcomeUnknown(f"Unexpected response format from OpenAI (request id {req_id}).") from e
        usage = dict(j.get("usage") or {})
        usage.update({k: j[k] for k in ("size", "quality", "output_format") if k in j})
        return GeneratedImage(data=data, mime="image/png", usage=usage, provider_request_id=req_id)
