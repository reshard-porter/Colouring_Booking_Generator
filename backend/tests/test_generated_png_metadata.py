"""Regression: real generated PNGs carry metadata (XMP / C2PA content credentials) that can contain '<svg' or
'<?xml' text. They must be accepted, and a paid image must never be lost if adding it fails."""
import io
import struct
import zlib

import pytest
from PIL import Image

from cbs import generation
from cbs.imaging import UploadRejected, validate_image_bytes
from cbs.providers.base import GeneratedImage
from cbs.providers.mock import MockProvider



def png_with_xml_metadata(w=1024, h=1536) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (w, h), 255).save(buf, "PNG")
    data = buf.getvalue()
    text = b'XML:com.adobe.xmp\x00\x00\x00\x00\x00<?xml version="1.0"?><x:xmpmeta><svg xmlns="http://www.w3.org/2000/svg"/></x:xmpmeta>'
    chunk = struct.pack(">I", len(text)) + b"iTXt" + text + struct.pack(">I", zlib.crc32(b"iTXt" + text) & 0xFFFFFFFF)
    return data[:33] + chunk + data[33:]  # right after IHDR, inside the first 512 bytes


def test_png_with_svg_text_in_metadata_is_accepted():
    data = png_with_xml_metadata()
    assert b"<svg" in data[:512]
    v = validate_image_bytes(data, max_bytes=40 << 20, max_pixels=60_000_000, max_side=12000)
    assert v.mime == "image/png" and (v.width, v.height) == (1024, 1536)
    with pytest.raises(UploadRejected, match="SVG"):
        validate_image_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', max_bytes=1 << 20, max_pixels=10**7, max_side=9000)


class MetadataProvider(MockProvider):
    def generate(self, prompt, *, size="1024x1536", quality=None, references=None):
        self.calls += 1
        return GeneratedImage(png_with_xml_metadata(), "image/png", usage={"total_tokens": 1})


def test_generated_png_with_metadata_is_imported(studio, runner):
    pid = studio.create_project("AI test", {"title": "Dino Picnic"})
    generation.plan_from_description(studio, pid, "Original friendly dinosaurs at a picnic", 10)
    sid = generation.autobook_status(studio, pid)["empty_scene_ids"][0]
    generation.set_test_provider(MetadataProvider())
    try:
        j = generation.start_generation(studio, runner, pid, [sid], {}, confirm=True)
        runner.run_one()
        assert runner.get(j["id"])["status"] == "succeeded", runner.get(j["id"])["error"]
        assert generation.generation_requests(studio, pid)[0]["state"] == "succeeded"
    finally:
        generation.set_test_provider(None)


def test_paid_image_saved_and_recoverable_when_adding_fails(studio, runner, monkeypatch):
    pid = studio.create_project("AI test", {"title": "Dino Picnic"})
    generation.plan_from_description(studio, pid, "Original friendly dinosaurs at a picnic", 10)
    sids = generation.autobook_status(studio, pid)["empty_scene_ids"][:1]
    generation.set_test_provider(MockProvider())
    real_import = studio.import_asset

    def broken(*a, **k):
        raise RuntimeError("simulated failure while adding")
    monkeypatch.setattr(studio, "import_asset", broken)
    try:
        j = generation.start_generation(studio, runner, pid, sids, {}, confirm=True)
        runner.run_one()
        jj = runner.get(j["id"])
        assert jj["status"] == "failed" and "saved at" in jj["error"]
        req = generation.generation_requests(studio, pid)[0]
        assert req["state"] == "received_not_imported"
        assert list((studio.settings.data_dir / "generated-originals").glob(f"{req['id']}.png"))
        assert generation.autobook_status(studio, pid)["unimported"] == 1
        monkeypatch.setattr(studio, "import_asset", real_import)
        ids = generation.recover_unimported(studio, pid)
        assert len(ids) == 1 and studio.asset(ids[0])["ai_involvement"] == "ai_generated"
        st = generation.autobook_status(studio, pid)
        assert st["unimported"] == 0 and any(p["version_id"] for p in st["pages"] if p["scene_id"] == sids[0])
    finally:
        generation.set_test_provider(None)
