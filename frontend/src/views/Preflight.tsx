import React, { useContext, useState } from "react";
import { api } from "../api";
import { ProjectCtx, go } from "../App";
import { Badge, ErrorBox, Loading, sevKind, useAsync, useToast } from "../ui";
import { ApproveAll } from "./ApproveAll";

const GROUPS: [string, string, string][] = [
  ["error", "Technical errors", "Must be fixed before a print-release package."],
  ["warning", "Technical warnings", "Likely problems worth fixing."],
  ["heuristic", "Artwork quality heuristics", "Automated estimates. They can be wrong; review the page and decide."],
  ["review", "Human publishing review", "Things only you can confirm: approvals, rights, AI involvement."],
];

export default function Preflight() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const rep = useAsync(() => api.get(`/api/projects/${pid}/preflight/latest`), [pid]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  async function run() {
    setRunning(true);
    setErr(null);
    try {
      await api.post(`/api/projects/${pid}/preflight`);
      await rep.reload();
      refresh();
      toast("ok", "Preflight finished.");
    } catch (e) {
      setErr(e);
    } finally {
      setRunning(false);
    }
  }
  const r = rep.data;
  return (
    <div className="page">
      <div className="row between">
        <div>
          <h1>Preflight</h1>
          <p className="lede">Checks your book against the dated KDP print profile. Passing preflight means “ready for your KDP review”, not “approved by Amazon”.</p>
        </div>
        <div className="row gap">
          <ApproveAll pid={pid} author={proj.spec.author} onDone={() => { refresh(); run(); }} />
          <button className="btn btn-primary" onClick={run} disabled={running}>{running ? "Checking…" : r ? "Re-run preflight" : "Run preflight"}</button>
        </div>
      </div>
      <ErrorBox error={err || rep.error} />
      {running && <Loading what="Checking pages, artwork, cover and provenance" />}
      {rep.loading && !r && <Loading />}
      {!r && !rep.loading && <p className="muted">No preflight run yet.</p>}
      {r && (
        <>
          <div className={`banner ${r.status === "blocked" ? "banner-bad" : r.status === "needs_review" ? "banner-review" : "banner-ok"}`}>
            <strong>{r.status_label}</strong> · {r.page_count} pages · run {new Date(r.created_at).toLocaleString()}
            {r.outdated && <span> · <Badge kind="warn">layout changed since this run – re-run</Badge></span>}
          </div>
          <p className="muted small">{r.disclaimer}</p>
          {GROUPS.map(([sev, title, desc]) => {
            const items = r.findings.filter((f: any) => f.severity === sev);
            return (
              <section key={sev} className="card">
                <h2>{title} <Badge kind={items.length ? sevKind[sev] : "ok"}>{items.length}</Badge></h2>
                <p className="muted small">{desc}</p>
                {items.length === 0 ? <p className="ok-text">None.</p> : (
                  <ul className="findings">
                    {items.map((f: any) => (
                      <li key={f.id}>
                        <code>{f.code}</code> {f.page_number ? <strong>p.{f.page_number}: </strong> : null}{f.message}
                        {f.page_id && <button className="btn btn-tiny" onClick={() => go(`/p/${pid}/editor/${f.page_id}`)}>Open page</button>}
                        {f.code === "cover_stale" && <button className="btn btn-tiny" onClick={() => go(`/p/${pid}/cover`)}>Open cover</button>}
                        {f.detail?.names && <details><summary className="small">Show {f.detail.names.length} file(s)</summary><span className="small muted">{f.detail.names.join(", ")}</span></details>}
                        {["rights_unknown", "demo_artwork", "ai_unknown"].includes(f.code) && <button className="btn btn-tiny" onClick={() => go(`/p/${pid}/artwork`)}>Open artwork</button>}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}
