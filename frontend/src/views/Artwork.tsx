import React, { useContext, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx, go } from "../App";
import { Badge, Empty, ErrorBox, Field, Loading, Modal, useAsync, useToast } from "../ui";

export const SOURCE_LABELS: Record<string, string> = {
  user_created: "Created by me", licensed: "Licensed", public_domain: "Public domain", ai_generated: "AI-generated",
  ai_assisted: "AI-assisted (I drew it, used AI tools)", demo_sample: "Demo sample", unknown: "Unknown",
};
const RIGHTS_LABELS: Record<string, string> = {
  owner_declared: "I own the rights", licensed_with_evidence: "Licensed (evidence recorded)", public_domain_declared: "Public domain (declared)", unknown: "Not declared",
};
const AI_LABELS: Record<string, string> = { none: "No AI", ai_generated: "AI-generated", ai_assisted: "AI-assisted", unknown: "Unknown" };

export default function Artwork() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const lib = useAsync(() => api.get(`/api/projects/${pid}/assets`), [pid]);
  const [decl, setDecl] = useState({ source_type: "user_created", rights_declaration: "owner_declared", ai_involvement: "none", creator: "", license: "", license_evidence: "" });
  const [kind, setKind] = useState("artwork");
  const [busy, setBusy] = useState<string | null>(null);
  const [errs, setErrs] = useState<string[]>([]);
  const [edit, setEdit] = useState<any>(null);
  const [placing, setPlacing] = useState<any>(null);
  const [filter, setFilter] = useState("all");
  const toast = useToast();

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const errors: string[] = [];
    let ok = 0;
    for (const [i, f] of Array.from(files).entries()) {
      setBusy(`Uploading ${i + 1} of ${files.length}: ${f.name}`);
      const fd = new FormData();
      fd.append("file", f);
      fd.append("declaration", JSON.stringify(decl));
      fd.append("kind", kind);
      try {
        await api.upload(`/api/projects/${pid}/assets`, fd);
        ok++;
      } catch (e: any) {
        errors.push(`${f.name}: ${e.message}`);
      }
    }
    setBusy(null);
    setErrs(errors);
    if (ok) toast("ok", `Imported ${ok} file(s). Originals are kept unchanged.`);
    lib.reload();
  }

  const assets = (lib.data || []).filter((a: any) => filter === "all" || a.kind === filter);
  return (
    <div className="page">
      <h1>Artwork library</h1>
      <p className="lede">Import PNG or JPEG line art. Every file keeps its original, its history, and what you declare about who made it and your right to use it.</p>
      <div className="split">
        <section className="card">
          <h2>Import files</h2>
          <div className="grid2">
            <Field label="Who made it?">
              <select value={decl.source_type} onChange={(e) => setDecl({ ...decl, source_type: e.target.value, ai_involvement: e.target.value === "ai_generated" ? "ai_generated" : e.target.value === "ai_assisted" ? "ai_assisted" : decl.ai_involvement })}>
                {Object.entries(SOURCE_LABELS).filter(([k]) => k !== "demo_sample").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Your rights" help="This is your own declaration. The app never guesses rights from a file name.">
              <select value={decl.rights_declaration} onChange={(e) => setDecl({ ...decl, rights_declaration: e.target.value })}>
                {Object.entries(RIGHTS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="AI involvement" help="AI-generated: an AI tool created the image (it stays AI-generated even after you edit it). AI-assisted: you created it and used AI tools to help.">
              <select value={decl.ai_involvement} onChange={(e) => setDecl({ ...decl, ai_involvement: e.target.value })}>
                {Object.entries(AI_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label="Creator / attribution"><input value={decl.creator} onChange={(e) => setDecl({ ...decl, creator: e.target.value })} /></Field>
            <Field label="License"><input value={decl.license} onChange={(e) => setDecl({ ...decl, license: e.target.value })} placeholder="e.g. commercial license #123" /></Field>
            <Field label="License evidence"><input value={decl.license_evidence} onChange={(e) => setDecl({ ...decl, license_evidence: e.target.value })} placeholder="receipt / URL / note" /></Field>
            <Field label="Use as">
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="artwork">Interior artwork</option>
                <option value="cover_art">Cover art</option>
                <option value="reference">Character reference</option>
                <option value="template">KDP cover template (alignment overlay only)</option>
              </select>
            </Field>
          </div>
          <label className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}>
            <input type="file" accept="image/png,image/jpeg" multiple onChange={(e) => { upload(e.target.files); e.target.value = ""; }} />
            <strong>Drop PNG/JPEG files here</strong> or click to choose
            <span className="muted small">Max 40 MB each. SVG is not supported in this version (it can contain scripts); export SVG as a 300 DPI PNG.</span>
          </label>
          {busy && <Loading what={busy} />}
          {errs.length > 0 && <div className="error-box" role="alert"><strong>Some files were rejected:</strong><ul>{errs.map((e) => <li key={e}>{e}</li>)}</ul></div>}
        </section>
        <Generate />
      </div>

      <section className="card">
        <div className="row between">
          <h2>Library <Badge>{lib.data?.length ?? 0}</Badge></h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by kind">
            <option value="all">All kinds</option><option value="artwork">Interior artwork</option><option value="cover_art">Cover art</option>
            <option value="reference">References</option><option value="template">Templates</option>
          </select>
        </div>
        <ErrorBox error={lib.error} retry={lib.reload} />
        {lib.loading && !lib.data && <Loading />}
        {assets.length === 0 && !lib.loading && <Empty title="No artwork yet"><p>Import files above.</p></Empty>}
        <div className="asset-grid">
          {assets.map((a: any) => {
            const cur = a.versions.find((v: any) => v.id === a.current_version_id) || a.versions[a.versions.length - 1];
            return (
              <div key={a.id} className="card asset">
                <img src={img(cur.id, 300)} alt={a.display_name} loading="lazy" />
                <div className="asset-name" title={a.display_name}>{a.display_name}</div>
                <div className="row gap wrap">
                  <Badge kind={a.source_type === "demo_sample" ? "review" : a.ai_involvement === "ai_generated" ? "info" : "neutral"}>{SOURCE_LABELS[a.source_type]}</Badge>
                  {a.rights_declaration === "unknown" && <Badge kind="warn">rights?</Badge>}
                  <Badge kind={a.review_status === "approved" ? "ok" : a.review_status === "unreviewed" ? "neutral" : "warn"}>{a.review_status}</Badge>
                  <Badge>{cur.width_px}×{cur.height_px}px</Badge>
                  {a.versions.length > 1 && <Badge>v{cur.version_no}</Badge>}
                </div>
                <div className="row gap wrap">
                  <button className="btn btn-small" onClick={() => setEdit(a)}>Details</button>
                  {a.kind === "artwork" && <button className="btn btn-small" onClick={() => setPlacing({ asset: a, version: cur })}>Place on page…</button>}
                  {a.kind === "artwork" && <button className="btn btn-small" onClick={async () => { await api.post(`/api/versions/${cur.id}/cover-art`); toast("ok", "Created a colored cover version (in Cover art)."); lib.reload(); }}>Make cover art</button>}
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {edit && <AssetDetails asset={edit} onClose={() => { setEdit(null); lib.reload(); refresh(); }} />}
      {placing && <PlaceModal {...placing} onClose={() => setPlacing(null)} />}
    </div>
  );
}

function AssetDetails({ asset, onClose }: any) {
  const [a, setA] = useState(asset);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  async function save() {
    try {
      const r = await api.patch(`/api/assets/${a.id}`, {
        display_name: a.display_name, source_type: a.source_type, creator: a.creator, license: a.license, license_evidence: a.license_evidence,
        rights_declaration: a.rights_declaration, ai_involvement: a.ai_involvement, review_status: a.review_status, review_notes: a.review_notes,
      });
      setA(r);
      toast("ok", "Provenance saved.");
      onClose();
    } catch (e) {
      setErr(e);
    }
  }
  const set = (k: string) => (e: any) => setA({ ...a, [k]: e.target.value });
  return (
    <Modal title={a.display_name} onClose={onClose} wide>
      <div className="split">
        <div>
          <img className="detail-img" src={img(a.current_version_id, 800)} alt="" />
          <h3>Versions (immutable)</h3>
          <ol className="versions">
            {a.versions.map((v: any) => (
              <li key={v.id}>
                v{v.version_no}: {v.operation?.type === "original_import" ? "original import" : v.operation?.type} · {v.width_px}×{v.height_px}px
                {v.upscaled && <Badge kind="warn">enlarged from {v.original_width_px}px – no new detail</Badge>}
                <span className="muted small"> sha256 {v.sha256.slice(0, 12)}…</span>
              </li>
            ))}
          </ol>
          {a.generation && <><h3>Generation record</h3><pre className="pre">{JSON.stringify(a.generation, null, 2)}</pre></>}
        </div>
        <div className="form-grid">
          {a.is_demo && <p className="note">Demonstration sample drawn by this app's code (not AI, not commercially reviewed). Replace it or confirm before publishing.</p>}
          <Field label="Name"><input value={a.display_name} onChange={set("display_name")} /></Field>
          <Field label="Source"><select value={a.source_type} onChange={set("source_type")}>{Object.entries(SOURCE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="AI involvement"><select value={a.ai_involvement} onChange={set("ai_involvement")}>{Object.entries(AI_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Rights"><select value={a.rights_declaration} onChange={set("rights_declaration")}>{Object.entries(RIGHTS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Creator"><input value={a.creator || ""} onChange={set("creator")} /></Field>
          <Field label="License"><input value={a.license || ""} onChange={set("license")} /></Field>
          <Field label="License evidence"><input value={a.license_evidence || ""} onChange={set("license_evidence")} /></Field>
          <Field label="Review status"><select value={a.review_status} onChange={set("review_status")}><option value="unreviewed">Unreviewed</option><option value="approved">Approved</option><option value="needs_changes">Needs changes</option><option value="rejected">Rejected</option></select></Field>
          <Field label="Review notes"><textarea rows={3} value={a.review_notes || ""} onChange={set("review_notes")} /></Field>
          <ErrorBox error={err} />
          <button className="btn btn-primary" onClick={save}>Save</button>
        </div>
      </div>
    </Modal>
  );
}

function PlaceModal({ asset, version, onClose }: any) {
  const { proj, refresh } = useContext(ProjectCtx);
  const illus = proj.pages.filter((p: any) => p.kind === "illustration");
  const toast = useToast();
  async function place(page: any) {
    if (page.elements.some((e: any) => e.kind === "image") && !confirm("Replace the artwork on this page?")) return;
    await api.post(`/api/pages/${page.id}/place`, { version_id: version.id, fit: "safe" });
    await refresh();
    toast("ok", "Placed and fitted to the safe area.");
    onClose();
    go(`/p/${proj.project.id}/editor/${page.id}`);
  }
  return (
    <Modal title={`Place “${asset.display_name}”`} onClose={onClose}>
      <p className="muted">Pick an illustration page. Empty pages are listed first.</p>
      <div className="place-list">
        {[...illus].sort((a: any, b: any) => +a.elements.some((e: any) => e.kind === "image") - +b.elements.some((e: any) => e.kind === "image")).map((p: any) => (
          <button key={p.id} className="btn place-item" onClick={() => place(p)}>
            {p.label} {p.elements.some((e: any) => e.kind === "image") ? <Badge>has art</Badge> : <Badge kind="ok">empty</Badge>}
          </button>
        ))}
      </div>
    </Modal>
  );
}

function Generate() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const st = useAsync(() => api.get("/api/ai/status"), []);
  const gens = useAsync(() => api.get(`/api/projects/${pid}/generations`), [pid]);
  const [sel, setSel] = useState<string[]>([]);
  const [size, setSize] = useState("1024x1536");
  const [quality, setQuality] = useState("high");
  const [est, setEst] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  if (st.loading) return <section className="card"><Loading what="Checking AI provider" /></section>;
  const configured = st.data?.status?.configured;
  return (
    <section className="card">
      <h2>Optional: AI generation</h2>
      {!configured ? (
        <div className="setup-state">
          <p><strong>No image provider configured.</strong> Everything else in the app works without one: import your own art or use the sample.</p>
          <p className="muted small">AI generation is a paid external service: it is not free, and outputs are not guaranteed to be consistent, exclusive or copyrightable. To set it up, add an API key in <a href="#/settings">Settings</a>.</p>
        </div>
      ) : (
        <>
          {!st.data.status.live && <p className="note">⚠ {st.data.status.note}</p>}
          <p className="muted small">Provider: {st.data.status.provider} · model {st.data.status.model}. {st.data.capabilities.resolution_note}</p>
          <Field label="Scenes to generate (start with ONE candidate)">
            <select multiple size={6} value={sel} onChange={(e) => setSel(Array.from(e.target.selectedOptions).map((o) => o.value))}>
              {proj.scenes.map((s: any, i: number) => <option key={s.id} value={s.id}>#{i + 1} {s.subject} – {s.action}</option>)}
            </select>
          </Field>
          <div className="row gap">
            <Field label="Size"><select value={size} onChange={(e) => setSize(e.target.value)}>{st.data.capabilities.sizes.map((s: string) => <option key={s}>{s}</option>)}</select></Field>
            <Field label="Quality"><select value={quality} onChange={(e) => setQuality(e.target.value)}>{st.data.capabilities.quality.map((s: string) => <option key={s}>{s}</option>)}</select></Field>
          </div>
          <button className="btn" disabled={!sel.length} onClick={async () => { setErr(null); setEst(await api.post(`/api/projects/${pid}/generate/estimate`, { scene_ids: sel, settings: { size, quality } })); }}>
            Review cost & settings
          </button>
          {est && (
            <div className="estimate">
              <dl className="facts">
                <dt>Images</dt><dd>{est.count}</dd>
                <dt>Settings</dt><dd>{size}, {quality}</dd>
                <dt>Estimated cost</dt><dd>{est.estimated_cost}{est.estimated_cost === "unknown" ? " (enter your per-image estimate in Settings)" : ""}</dd>
                <dt>Spending limit</dt><dd>{est.budget.spending_limit ?? "not set"}</dd>
                <dt>Estimated so far</dt><dd>{est.budget.estimated_spent}</dd>
                <dt>Provider-reported</dt><dd>{est.budget.provider_reported_cost ?? "not reported"}</dd>
              </dl>
              <p className="muted small">{est.warning}</p>
              {est.problems.map((p: string) => <p key={p} className="warn-text">{p}</p>)}
              <button className="btn btn-primary" disabled={!est.allowed} onClick={async () => {
                try { await api.post(`/api/projects/${pid}/generate`, { scene_ids: sel, settings: { size, quality }, confirm: true }); toast("info", "Generation started – see Export → Jobs for progress."); setEst(null); setTimeout(() => { gens.reload(); refresh(); }, 1500); }
                catch (e) { setErr(e); }
              }}>Generate {est.count} image{est.count > 1 ? "s" : ""}</button>
            </div>
          )}
          <ErrorBox error={err} />
          {(gens.data || []).length > 0 && (
            <>
              <h3>Requests</h3>
              <ul className="gen-list">
                {gens.data.map((g: any) => <li key={g.id}><Badge kind={g.state === "succeeded" ? "ok" : g.state === "unknown_outcome" ? "bad" : "neutral"}>{g.state.replace("_", " ")}</Badge> {g.prompt.slice(0, 80)}… {g.error && <span className="warn-text">{g.error}</span>}</li>)}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
