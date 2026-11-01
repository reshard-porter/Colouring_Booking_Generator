import React, { useContext, useEffect, useState } from "react";
import { api } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, useAsync, useToast } from "../ui";

export function useJobs(pid: string) {
  const jobs = useAsync(() => api.get(`/api/jobs?project_id=${pid}`), [pid]);
  const active = (jobs.data || []).some((j: any) => ["queued", "running"].includes(j.status));
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => jobs.reload(), 1000);
    return () => clearInterval(t);
  }, [active]);
  return { jobs, active };
}

export function JobList({ jobs, onChange }: any) {
  const toast = useToast();
  return (
    <ul className="jobs">
      {(jobs || []).slice(0, 12).map((j: any) => (
        <li key={j.id} className={`job job-${j.status}`}>
          <div className="row between">
            <span><strong>{j.type.replace(/_/g, " ")}</strong> {j.params?.mode && <Badge>{j.params.mode}</Badge>} <Badge kind={j.status === "succeeded" ? "ok" : j.status === "failed" || j.status === "needs_attention" ? "bad" : j.status === "canceled" ? "neutral" : "info"}>{j.status.replace("_", " ")}</Badge></span>
            <span className="muted small">{new Date(j.created_at).toLocaleTimeString()}{j.attempts > 1 ? ` · attempt ${j.attempts}` : ""}</span>
          </div>
          {["queued", "running"].includes(j.status) && (
            <>
              {j.progress != null ? <progress max={1} value={j.progress} aria-label="Progress" /> : <progress aria-label="Working" />}
              <div className="row between small"><span>{j.progress_label || (j.status === "queued" ? "Waiting to start" : "")}</span>
                <button className="btn btn-tiny" onClick={async () => { await api.post(`/api/jobs/${j.id}/cancel`); onChange(); }}>{j.cancel_requested ? "Canceling…" : "Cancel"}</button></div>
            </>
          )}
          {j.error && <p className="warn-text small">{j.error}</p>}
          {["failed", "canceled"].includes(j.status) && j.type !== "generate_images" && (
            <button className="btn btn-tiny" onClick={async () => { try { await api.post(`/api/jobs/${j.id}/retry`); onChange(); } catch (e: any) { toast("err", e.message); } }}>Retry</button>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function Export() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const { jobs, active } = useJobs(pid);
  const exps = useAsync(() => api.get(`/api/projects/${pid}/exports`), [pid]);
  const pf = useAsync(() => api.get(`/api/projects/${pid}/preflight/latest`), [pid]);
  const [ack, setAck] = useState(false);
  const [sources, setSources] = useState(false);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  useEffect(() => { if (!active) { exps.reload(); } }, [active]);

  async function start(mode: "draft" | "release") {
    setErr(null);
    try {
      await api.post(`/api/projects/${pid}/exports`, { mode, include_sources: sources, acknowledged_review: ack });
      toast("info", `${mode === "release" ? "Release" : "Draft"} export started.`);
      jobs.reload();
    } catch (e: any) {
      setErr(e);
    }
  }
  const r = pf.data;
  const errors = r?.counts?.error ?? null;
  const reviews = (r?.findings || []).filter((f: any) => f.severity === "review");
  return (
    <div className="page">
      <h1>Export publishing package</h1>
      <p className="lede">Exports render from a frozen snapshot of the project, then the real PDF files are re-opened and checked (page count, sizes, fonts, blank pages, barcode area).</p>
      <div className="split">
        <section className="card">
          <h2>Draft package</h2>
          <p className="small">Always available – for proofreading and sharing previews. Clearly labelled DRAFT in the checklist and contact sheet.</p>
          <label className="check-inline"><input type="checkbox" checked={sources} onChange={(e) => setSources(e.target.checked)} /> Include source artwork files</label>
          <button className="btn" disabled={active} onClick={() => start("draft")}>Export draft package</button>
        </section>
        <section className="card">
          <h2>Print-release package</h2>
          {!r && <p className="warn-text">Run preflight first.</p>}
          {r && r.outdated && <p className="warn-text">Your layout changed after the last preflight. The export re-runs preflight on its snapshot anyway.</p>}
          {r && errors > 0 && <p className="warn-text">Blocked: {errors} technical error(s). <a href={`#/p/${pid}/preflight`}>Fix them in Preflight</a>.</p>}
          {r && errors === 0 && reviews.length > 0 && (
            <>
              <p className="small">Confirm you have reviewed these items:</p>
              <ul className="small">{reviews.map((f: any) => <li key={f.id}>{f.message}</li>)}</ul>
              <label className="check-inline"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I reviewed these items and accept responsibility for them</label>
            </>
          )}
          <button className="btn btn-primary" disabled={active || !r || errors > 0 || (reviews.length > 0 && !ack)} onClick={() => start("release")}>Export print-release package</button>
          {proj.project.release_approval && <p className="muted small">Last release package: {new Date(proj.project.release_approval.at).toLocaleString()} (snapshot {proj.project.release_approval.snapshot_sha?.slice(0, 10)}). Any later edit means you should export again.</p>}
        </section>
      </div>
      <ErrorBox error={err} />
      <section className="card">
        <h2>Jobs</h2>
        <JobList jobs={jobs.data} onChange={jobs.reload} />
        {!jobs.data?.length && <p className="muted">No jobs yet.</p>}
      </section>
      <section className="card">
        <h2>Finished exports</h2>
        {(exps.data || []).length === 0 && <p className="muted">Nothing exported yet.</p>}
        {(exps.data || []).map((e: any) => (
          <div key={e.id} className="export">
            <div className="row between">
              <span><Badge kind={e.mode === "release" ? "ok" : "review"}>{e.mode === "release" ? "print-release" : "draft"}</Badge> <Badge kind={e.status === "succeeded" ? "ok" : e.status === "failed" ? "bad" : "neutral"}>{e.status}</Badge> {new Date(e.created_at).toLocaleString()}</span>
              {e.files?.__zip__ && <a className="btn btn-primary btn-small" href={`/api/exports/${e.id}/files/zip`} download>Download ZIP</a>}
            </div>
            {e.files && (
              <ul className="files">
                {Object.entries(e.files).filter(([k]) => k !== "__zip__").map(([k, size]: any) => (
                  <li key={k}><a href={`/api/exports/${e.id}/files/${k}`} target="_blank" rel="noreferrer">{k}</a> <span className="muted small">{(size / 1024).toFixed(0)} KB</span></li>
                ))}
              </ul>
            )}
            {e.verification && (
              <p className="small">
                Verified: interior {e.verification.interior.info.page_count} pages ({e.verification.interior.info.page_sizes_pt.map((s: number[]) => s.join("×")).join(", ")} pt), fonts embedded: {e.verification.interior.info.fonts_embedded.length}, blank pages checked: {e.verification.interior.info.blank_pages_verified}; cover {e.verification.cover.info.size_in.join(" × ")} in, barcode area white: {String(e.verification.cover.info.barcode_area_white)}.
              </p>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
