import React, { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, Field, Loading, useAsync, useToast } from "../ui";

export default function Settings() {
  const ai = useAsync(() => api.get("/api/ai/status"), []);
  const meta = useAsync(() => api.get("/api/meta"), []);
  const projects = useAsync(() => api.get("/api/projects"), []);
  const [s, setS] = useState<any>({ model: "", per_image_estimate: "", spending_limit: "" });
  const [key, setKey] = useState("");
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  useEffect(() => { if (ai.data) setS({ model: ai.data.status.model, per_image_estimate: "", spending_limit: "", ...ai.data.settings }); }, [ai.data]);
  async function saveAI() {
    try {
      ai.setData(await api.put("/api/ai/settings", s));
      toast("ok", "AI settings saved.");
    } catch (e) {
      setErr(e);
    }
  }
  return (
    <div className="page">
      <h1>Settings</h1>
      <section className="card form-grid">
        <h2>Optional AI image provider</h2>
        {ai.loading && <Loading />}
        {ai.data && (
          <>
            <p>Status: <strong>{ai.data.status.configured ? "configured" : "not configured"}</strong> · provider {ai.data.status.provider} {ai.data.key_source && <span className="muted">(key from {ai.data.key_source})</span>}</p>
            <p className="muted small">The key is stored only on this computer (environment variable OPENAI_API_KEY, or a private file in the app data folder). It is never shown again, never put in exports, and never sent anywhere except the provider when you click Generate. Generation is billed by the provider – check their current prices and terms, including commercial-use terms.</p>
            <Field label="API key (write-only)"><input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={ai.data.status.configured ? "•••••••• (set)" : "paste key"} /></Field>
            <div className="row gap">
              <button className="btn" disabled={!key} onClick={async () => { ai.setData(await api.put("/api/ai/key", { api_key: key })); setKey(""); toast("ok", "Key saved locally."); }}>Save key</button>
              <button className="btn btn-ghost" onClick={async () => { ai.setData(await api.put("/api/ai/key", { api_key: null })); toast("ok", "Key removed."); }}>Remove key</button>
            </div>
            <Field label="Model" hint="gpt-image-1 was shut down by OpenAI on 2026-10-23.">
              <select value={s.model || ai.data.status.model} onChange={(e) => setS({ ...s, model: e.target.value })}>
                {(ai.data.capabilities.models || []).map((m: any) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </Field>
            {ai.data.status.note && <p className="warn-text small">{ai.data.status.note}</p>}
            <button className="btn btn-small" onClick={async () => { const r = await api.post("/api/ai/test"); toast(r.ok ? "ok" : "err", r.message); }}>Test connection (free)</button>
            <Field label="Your per-image cost estimate" hint="From the provider's current price page. Leave blank if unknown; batches stay disabled until you set it.">
              <input type="number" step="0.001" min={0} value={s.per_image_estimate ?? ""} onChange={(e) => setS({ ...s, per_image_estimate: e.target.value })} />
            </Field>
            <Field label="Spending limit for this installation"><input type="number" step="0.01" min={0} value={s.spending_limit ?? ""} onChange={(e) => setS({ ...s, spending_limit: e.target.value })} /></Field>
            <ErrorBox error={err} />
            <button className="btn btn-primary" onClick={saveAI}>Save AI settings</button>
          </>
        )}
      </section>
      <section className="card">
        <h2>Data & backups</h2>
        {meta.data && <p>Data folder: <code>{meta.data.data_dir}</code> · server {meta.data.bind} (localhost only) · version {meta.data.version} ({meta.data.build})</p>}
        <p className="muted small">Projects autosave to a local SQLite database. Original files are never modified. Nothing is sent over the network unless you use AI generation. No analytics.</p>
        <ul className="files">
          {(projects.data || []).map((p: any) => (
            <li key={p.id}>
              {p.name} – <a href={`/api/projects/${p.id}/backup`}>download portable backup (.cbsproj)</a>{" "}
              <button className="btn btn-tiny" onClick={async () => { const r = await api.post(`/api/projects/${p.id}/backup-now`); toast("ok", `Backup saved: ${r.saved}`); }}>Save backup in data folder</button>
            </li>
          ))}
        </ul>
        <p className="muted small">Restore a backup from the projects page with “Import project…”.</p>
      </section>
      <section className="card">
        <h2>Promo video</h2>
        {meta.data && <p>{meta.data.video.available ? "FFmpeg found – promo videos enabled." : meta.data.video.reason}</p>}
      </section>
    </div>
  );
}
