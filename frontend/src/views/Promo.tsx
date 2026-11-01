import React, { useContext, useState } from "react";
import { api } from "../api";
import { ProjectCtx } from "../App";
import { ErrorBox, Field, Loading, useAsync, useToast } from "../ui";
import { JobList, useJobs } from "./Export";

export default function Promo() {
  const { proj } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const st = useAsync(() => api.get("/api/video/status"), []);
  const { jobs } = useJobs(pid);
  const [dur, setDur] = useState(12);
  const [caps, setCaps] = useState(`${proj.assembly.illustration_count} pages of coloring fun\nBig shapes for little hands`);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  const approved = proj.pages.filter((p: any) => p.kind === "illustration" && p.approved).length;
  const videos = (jobs.data || []).filter((j: any) => j.type === "promo_video" && j.status === "succeeded");
  return (
    <div className="page">
      <h1>Promo video (optional)</h1>
      <p className="lede">A short, silent vertical video (1080 × 1920) with a page reveal, a simple coloring reveal and a gentle zoom, made from your approved pages. It's simulated page movement for social media – the printed book doesn't move, and this isn't part of any Kindle product.</p>
      {st.loading && <Loading />}
      {st.data && !st.data.available && <div className="banner banner-info">Video rendering is disabled: {st.data.reason}</div>}
      {st.data?.available && (
        <section className="card form-grid">
          {approved === 0 && <p className="warn-text">Approve at least one illustration page first (Pages & layout).</p>}
          <Field label={`Duration: ${dur} s`}><input type="range" min={4} max={30} value={dur} onChange={(e) => setDur(+e.target.value)} /></Field>
          <Field label="Captions (one per page shown)"><textarea rows={3} value={caps} onChange={(e) => setCaps(e.target.value)} /></Field>
          <p className="muted small">Exported silent. Add music later only if you have the rights to it.</p>
          <ErrorBox error={err} />
          <button className="btn btn-primary" disabled={approved === 0} onClick={async () => {
            try { await api.post(`/api/projects/${pid}/promo`, { duration_s: dur, captions: caps.split("\n").filter(Boolean) }); toast("info", "Rendering video…"); jobs.reload(); } catch (e) { setErr(e); }
          }}>Render MP4</button>
        </section>
      )}
      <section className="card">
        <h2>Jobs</h2>
        <JobList jobs={(jobs.data || []).filter((j: any) => j.type === "promo_video")} onChange={jobs.reload} />
      </section>
      {videos.map((j: any) => (
        <section key={j.id} className="card">
          <h3>Video {new Date(j.finished_at).toLocaleString()}</h3>
          <video className="promo" src={`/api/videos/${j.result.file}`} controls muted playsInline />
          <p className="small muted">Verified with ffprobe: {j.result.verification.width}×{j.result.verification.height}, {j.result.verification.codec}, {j.result.verification.duration_s}s, {j.result.verification.audio_streams} audio streams, full decode OK: {String(j.result.verification.decode_ok)}.</p>
          <a className="btn btn-small" href={`/api/videos/${j.result.file}`} download>Download MP4</a>
        </section>
      ))}
    </div>
  );
}
