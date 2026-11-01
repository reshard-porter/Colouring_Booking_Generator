"""Contract tests for the OpenAI adapter against the documented request/response format (no network, no cost).
These simulate OpenAI with httpx.MockTransport; they are NOT live tests."""
import base64
import io
import json

import httpx
import pytest
from PIL import Image

from cbs.providers.base import ProviderOutcomeUnknown, ProviderRequestFailed
from cbs.providers.openai_images import DEFAULT_MODEL, OpenAIImagesProvider, validate_size


def png(w=64, h=96):
    b = io.BytesIO()
    Image.new("L", (w, h), 255).save(b, "PNG")
    return b.getvalue()


def ok_response(request):
    return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(png()).decode()}],
                                     "usage": {"input_tokens": 50, "output_tokens": 4000, "total_tokens": 4050},
                                     "size": "2400x3200", "quality": "high", "output_format": "png"},
                          headers={"x-request-id": "req_123"})


def provider(handler, model=DEFAULT_MODEL, sleeps=None):
    return OpenAIImagesProvider("sk-test", model=model, transport=httpx.MockTransport(handler),
                                sleep=(lambda s: sleeps.append(s)) if sleeps is not None else (lambda s: None))


def test_generation_request_matches_docs():
    seen = {}

    def h(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return ok_response(req)
    res = provider(h).generate("a turtle", size="2400x3200", quality="high")
    assert seen["url"] == "https://api.openai.com/v1/images/generations"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"] == {"model": "gpt-image-2.5-sunburst", "prompt": "a turtle", "size": "2400x3200", "n": 1,
                            "output_format": "png", "background": "opaque", "quality": "high"}
    assert Image.open(io.BytesIO(res.data)).size == (64, 96)
    assert res.usage["total_tokens"] == 4050 and res.usage["size"] == "2400x3200" and res.provider_request_id == "req_123"


def test_reference_images_use_edits_endpoint_with_images_array():
    seen = {}

    def h(req):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return ok_response(req)
    provider(h).generate("new scene", size="1632x2176", references=[png(), png()])
    assert seen["url"].endswith("/v1/images/edits")
    imgs = seen["body"]["images"]
    assert len(imgs) == 2 and imgs[0]["image_url"].startswith("data:image/png;base64,")
    assert "input_fidelity" not in seen["body"]


@pytest.mark.parametrize("model,size,ok", [
    ("gpt-image-2.5-sunburst", "2400x3200", True), ("gpt-image-2.5-flare", "1632x2176", True), ("gpt-image-2", "3840x2160", True),
    ("gpt-image-2.5-sunburst", "2400x3210", False), ("gpt-image-2.5-sunburst", "1008x3600", False),
    ("gpt-image-2.5-sunburst", "4000x2000", False), ("gpt-image-2.5-sunburst", "512x512", False),
    ("gpt-image-1.5", "2400x3200", False), ("gpt-image-1.5", "1024x1536", True)])
def test_size_rules(model, size, ok):
    assert (validate_size(model, size) is None) == ok


def test_retired_model_and_status():
    p = OpenAIImagesProvider("sk-x", model="gpt-image-1")
    st = p.status()
    assert not st["configured"] and "shut down" in st["note"]
    with pytest.raises(ProviderRequestFailed, match="shut down"):
        p.generate("x", size="1024x1536")
    assert OpenAIImagesProvider(None).status()["configured"] is False
    caps = OpenAIImagesProvider("k").capabilities()
    assert caps["sizes"][0] == "2400x3200" and "max" in caps["quality"]
    assert OpenAIImagesProvider("k", model="gpt-image-1.5").capabilities()["sizes"] == ["1024x1536"]


@pytest.mark.parametrize("status,body,match", [
    (401, {"error": {"message": "Incorrect API key provided"}}, "API key"),
    (403, {"error": {"message": "Your organization must be verified to use the model gpt-image-2.5-sunburst."}}, "settings/organization/general"),
    (404, {"error": {"message": "model not found"}}, "isn't available"),
    (400, {"error": {"message": "Your request was rejected by the safety system."}}, "safety"),
    (429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details."}}, "credit"),
])
def test_definite_rejections_are_failed_with_friendly_messages(status, body, match):
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(status, json=body)
    with pytest.raises(ProviderRequestFailed, match=match):
        provider(h).generate("x", size="2400x3200")
    assert len(calls) == 1  # never retried


def test_rate_limit_is_retried_safely():
    calls, sleeps = [], []

    def h(req):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "Rate limit reached"}}, headers={"retry-after": "2"}) if len(calls) < 3 else ok_response(req)
    provider(h, sleeps=sleeps).generate("x", size="2400x3200")
    assert len(calls) == 3 and sleeps == [2.0, 2.0]


def test_unknown_outcomes_are_not_retried():
    calls = []

    def timeout(req):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(ProviderOutcomeUnknown):
        provider(timeout).generate("x", size="2400x3200")
    assert len(calls) == 1
    with pytest.raises(ProviderOutcomeUnknown):
        provider(lambda r: httpx.Response(502, text="bad gateway")).generate("x", size="2400x3200")
    with pytest.raises(ProviderOutcomeUnknown):
        provider(lambda r: httpx.Response(200, json={"data": []})).generate("x", size="2400x3200")


def test_connection_refused_retried_then_failed():
    calls = []

    def h(req):
        calls.append(1)
        raise httpx.ConnectError("refused", request=req)
    with pytest.raises(ProviderRequestFailed, match="connect"):
        provider(h).generate("x", size="2400x3200")
    assert len(calls) == 4


def test_free_connection_check():
    def h(req):
        assert req.method == "GET" and str(req.url).endswith("/v1/models/gpt-image-2.5-sunburst")
        return httpx.Response(200, json={"id": "gpt-image-2.5-sunburst", "object": "model"})
    assert provider(h).test_connection()["ok"]
    r = provider(lambda req: httpx.Response(401, json={"error": {"message": "bad key"}})).test_connection()
    assert not r["ok"] and "API key" in r["message"]
    assert not OpenAIImagesProvider(None).test_connection()["ok"]
