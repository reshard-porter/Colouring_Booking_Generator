import React, { useContext, useEffect, useState } from "react";
import { api } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Field, useAsync, useToast } from "../ui";
import { HeroTeam, MasterStyle, StylePresets } from "./Heroes";

export default function Plan() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const sc = useAsync(() => api.get(`/api/projects/${pid}/scenes`), [pid]);
  const toast = useToast();
  const [style, setStyle] = useState<any>(proj.style_guide);
  useEffect(() => setStyle(proj.style_guide), [proj.style_guide]);

  async function draft(replace: boolean) {
    if (replace && !confirm("Replace all existing scenes with a new draft? Pages keep their artwork.")) return;
    const r = await api.post(`/api/projects/${pid}/scenes/draft`, { replace });
    sc.setData(r);
    refresh();
    toast("ok", "Drafted a scene plan. Edit anything you like.");
  }
  async function saveStyle() {
    await api.put(`/api/projects/${pid}/style`, style);
    refresh();
    toast("ok", "Style guide saved.");
  }
  const warnFor = (id: string) => (sc.data?.warnings || []).filter((w: any) => w.scene_ids.includes(id));

  return (
    <div className="page">
      <h1>Plan & style</h1>
      <p className="lede">Describe each illustration before drawing or generating it. Planning works fully offline – no AI needed.</p>
      <StylePresets pid={pid} current={style.preset} style={style} kidsFirst={!((proj.spec.audience || "").toLowerCase().startsWith("adult"))} onApplied={(sg: any) => { setStyle(sg); refresh(); }} />

      <section className="card">
        <div className="row between">
          <h2>Style guide</h2>
          <button className="btn btn-primary" onClick={saveStyle}>Save style guide</button>
        </div>
        <div className="grid2">
          <Field label="Outline weight"><input value={style.outline_weight} onChange={(e) => setStyle({ ...style, outline_weight: e.target.value })} /></Field>
          <Field label="Background density"><input value={style.background_density} onChange={(e) => setStyle({ ...style, background_density: e.target.value })} /></Field>
          <Field label="Level of detail"><input value={style.detail_level} onChange={(e) => setStyle({ ...style, detail_level: e.target.value })} /></Field>
          <Field label="Coloring spaces (large vs small)"><input value={style.coloring_spaces} onChange={(e) => setStyle({ ...style, coloring_spaces: e.target.value })} /></Field>
        </div>
        <Field label="Avoid (one per line)">
          <textarea rows={4} value={(style.avoid || []).join("\n")} onChange={(e) => setStyle({ ...style, avoid: e.target.value.split("\n") })} />
        </Field>
        <p className="note">{style.consistency_note}</p>
        <MasterStyle pid={pid} style={style} onSaved={(sg: any) => { setStyle(sg); refresh(); }} />
      </section>

      <HeroTeam pid={pid} style={style} setStyle={setStyle} save={saveStyle} />

      <section className="card">
        <div className="row between">
          <h2>Scene plan <Badge>{sc.data?.scenes?.length ?? 0} scenes</Badge></h2>
          <div className="row gap">
            <button className="btn" onClick={() => draft(false)}>Draft {proj.spec.illustration_count} scenes</button>
            <button className="btn btn-ghost" onClick={() => draft(true)}>Replace with new draft</button>
            <button className="btn" onClick={async () => { await api.post(`/api/projects/${pid}/scenes`, { subject: "", action: "", setting: "", composition: "", complexity: "" }); sc.reload(); }}>+ Blank scene</button>
          </div>
        </div>
        <ErrorBox error={sc.error} retry={sc.reload} />
        {(sc.data?.warnings || []).length > 0 && (
          <ul className="warn-list">
            {sc.data.warnings.map((w: any, i: number) => <li key={i}>{w.message}</li>)}
          </ul>
        )}
        <div className="scene-grid">
          {(sc.data?.scenes || []).map((s: any, i: number) => (
            <SceneCard key={s.id} n={i + 1} scene={s} warn={warnFor(s.id).length > 0} pid={pid} onChange={sc.reload} />
          ))}
        </div>
      </section>
    </div>
  );
}

function SceneCard({ scene, n, pid, onChange, warn }: any) {
  const [s, setS] = useState(scene);
  const [dirty, setDirty] = useState(false);
  const upd = (k: string) => (e: any) => { setS({ ...s, [k]: e.target.value }); setDirty(true); };
  async function save() {
    await api.put(`/api/projects/${pid}/scenes/${s.id}`, s);
    setDirty(false);
    onChange();
  }
  return (
    <div className={`card scene ${warn ? "scene-warn" : ""}`} onBlur={(e) => dirty && !e.currentTarget.contains(e.relatedTarget as Node) && save()}>
      <div className="row between"><strong>#{n}</strong>{dirty ? <Badge kind="warn">unsaved</Badge> : <Badge kind="ok">saved</Badge>}</div>
      <Field label="Your description for this page (overrides the fields below)"><textarea rows={3} maxLength={4000} value={s.description || ""} onChange={upd("description")} /></Field>
      {(["subject", "action", "setting", "composition", "complexity"] as const).map((k) => (
        <Field key={k} label={k[0].toUpperCase() + k.slice(1)}><input value={s[k] || ""} onChange={upd(k)} /></Field>
      ))}
      <button className="btn btn-small btn-ghost" onClick={async () => { await api.del(`/api/projects/${pid}/scenes/${s.id}`); onChange(); }}>Delete</button>
    </div>
  );
}
