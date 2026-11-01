"""Build the genuine sample package from the seeded project, in a throwaway data directory.

  python scripts/export_sample.py [output_dir]

Produces: the DRAFT publishing ZIP (demo art has undeclared rights, so a release package is
correctly blocked by human-review items unless acknowledged), rendered PNG previews, and a
promo MP4. For the video only, this script approves four demo pages – an owner action done here
purely to demonstrate the feature."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from cbs import exporter, preflight, video  # noqa: E402
from cbs.config import Settings  # noqa: E402
from cbs.jobs import JobRunner  # noqa: E402
from cbs.seed import seed_sample  # noqa: E402
from cbs.studio import Studio  # noqa: E402


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "sample-output").resolve()
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cbs-sample-"))
    st = Studio(Settings(data_dir=tmp))
    runner = JobRunner(st)
    print("Seeding sample project…")
    pid = seed_sample(st)
    rep = preflight.run_and_store(st, pid)
    print("Preflight:", rep["status_label"], rep["counts"])
    j = exporter.request_export(st, runner, pid, "draft")
    runner.run_one()
    j = runner.get(j["id"])
    assert j["status"] == "succeeded", j["error"]
    e = exporter.list_exports(st, pid)[0]
    zsrc = exporter.export_file_path(st, e["id"], "zip")
    shutil.copy(zsrc, out / zsrc.name)
    pkg = out / "package"
    if pkg.exists():
        shutil.rmtree(pkg)
    shutil.copytree(zsrc.parent / "package", pkg)
    print("Draft package:", out / zsrc.name)
    # release attempt without acknowledgement must be blocked (demo art has undeclared rights)
    j = exporter.request_export(st, runner, pid, "release", acknowledged_review=False)
    runner.run_one()
    print("Release attempt without review acknowledgement:", runner.get(j["id"])["status"], "-", runner.get(j["id"])["error"])
    if video.available()["available"]:
        for p in [p for p in st.pages(pid) if p["kind"] == "illustration"][:4]:
            st.set_page_approval(p["id"], True, "approved by export_sample.py for the promo demo only")
        j = runner.enqueue("promo_video", pid, {"duration_s": 12, "captions": ["40 island coloring pages", "Big shapes for little hands", "Blank back on every page", "Sample demo art"]})
        runner.run_one()
        j = runner.get(j["id"])
        assert j["status"] == "succeeded", j["error"]
        shutil.copy(st.settings.exports_dir / "videos" / j["result"]["file"], out / "promo-sample.mp4")
        print("Promo video:", out / "promo-sample.mp4", j["result"]["verification"])
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
