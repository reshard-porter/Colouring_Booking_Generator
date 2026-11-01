import React, { useContext, useEffect, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Field, Loading, useAsync, useToast } from "../ui";

export default function Cover() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const cov = useAsync(() => api.get(`/api/projects/${pid}/cover`), [pid]);
  const assets = useAsync(() => api.get(`/api/projects/${pid}/assets`), [pid]);
  const [d, setD] = useState<any>(null);
  const [stamp, setStamp] = useState(Date.now());
  const [ov, setOv] = useState({ guides: true, template: true });
  const [err, setErr] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  useEffect(() => { if (cov.data) setD(cov.data.data); }, [cov.data]);

  if (cov.loading && !cov.data) return <Loading what="Loading cover" />;
  if (cov.error) return <ErrorBox error={cov.error} retry={cov.reload} />;
  if (!d) return null;
  const c = cov.data;
  const g = c.geometry;
  const L = c.layout;
  async function save(patch: any = {}) {
    setSaving(true);
    setErr(null);
    try {
      const r = await api.put(`/api/projects/${pid}/cover`, { ...d, ...patch });
      cov.setData(r);
      setStamp(Date.now());
      refresh();
    } catch (e) {
      setErr(e);
    } finally {
      setSaving(false);
    }
  }
  const coverArt = (assets.data || []).filter((a: any) => a.kind === "cover_art");
  const interior = (assets.data || []).filter((a: any) => a.kind === "artwork");
  const templates = (assets.data || []).filter((a: any) => a.kind === "template");
  const set = (k: string, conv: (v: any) => any = (v) => v) => (e: any) => setD({ ...d, [k]: e.target.type === "checkbox" ? e.target.checked : conv(e.target.value) });
  const S = 100 / g.full_width_in; // percent per inch for overlay
  const box = (r: any, cls: string, label?: string) => (
    <div className={`ov ${cls}`} style={{ left: `${r.x * S}%`, top: `${(r.y / g.full_height_in) * 100}%`, width: `${r.w * S}%`, height: `${(r.h / g.full_height_in) * 100}%` }}>
      {label && <span>{label}</span>}
    </div>
  );
  const tpl = d.template_overlay_version_id;

  return (
    <div className="page">
      <h1>Cover designer</h1>
      <p className="lede">A single full-wrap PDF: back cover, spine, front cover, plus 0.125 in bleed on every outside edge.</p>
      {c.stale && (
        <div className="banner banner-bad" role="alert">
          Cover calculations are stale. {c.stale_reasons.join(" ")}
          <button className="btn btn-small" onClick={async () => { cov.setData(await api.post(`/api/projects/${pid}/cover/recalc`)); setStamp(Date.now()); refresh(); toast("ok", "Cover recalculated for the current page count."); }}>Recalculate now</button>
        </div>
      )}
      <div className="cover-stage">
        <div className="cover-preview" style={{ aspectRatio: `${g.full_width_in} / ${g.full_height_in}` }}>
          <img src={`/api/projects/${pid}/cover/preview.png?dpi=45&t=${stamp}`} alt="Cover preview rendered by the export engine" />
          {tpl && ov.template && <img className="tpl" src={img(tpl, 2000)} style={{ opacity: d.template_opacity }} alt="KDP template overlay (not printed)" />}
          {ov.guides && (
            <>
              {box({ x: g.bleed_in, y: g.bleed_in, w: g.full_width_in - 2 * g.bleed_in, h: g.full_height_in - 2 * g.bleed_in }, "ov-trim")}
              {box(g.spine, "ov-spine")}
              {box(g.back_safe, "ov-safe", "back safe area")}
              {box(g.front_safe, "ov-safe", "front safe area")}
              {box(g.barcode, "ov-barcode", "barcode (Amazon)")}
            </>
          )}
        </div>
        <div className="row gap wrap">
          <label className="check-inline"><input type="checkbox" checked={ov.guides} onChange={(e) => setOv({ ...ov, guides: e.target.checked })} /> Guides (trim, spine, safe areas, barcode)</label>
          {tpl && <label className="check-inline"><input type="checkbox" checked={ov.template} onChange={(e) => setOv({ ...ov, template: e.target.checked })} /> KDP template overlay</label>}
          <span className="muted small">Overlays are screen-only and never appear in cover.pdf.</span>
        </div>
      </div>
      <div className="split">
        <section className="card form-grid">
          <h2>Text</h2>
          <Field label="Title (blank = book title)"><input value={d.title || ""} placeholder={proj.spec.title} onChange={set("title")} /></Field>
          <Field label="Subtitle (blank = book subtitle)"><input value={d.subtitle ?? ""} placeholder={proj.spec.subtitle} onChange={set("subtitle")} /></Field>
          <Field label="Author (blank = book author)"><input value={d.author || ""} placeholder={proj.spec.author} onChange={set("author")} /></Field>
          <div className="grid3">
            <Field label="Title max pt"><input type="number" value={d.title_pt} onChange={set("title_pt", Number)} /></Field>
            <Field label="Subtitle pt"><input type="number" value={d.subtitle_pt} onChange={set("subtitle_pt", Number)} /></Field>
            <Field label="Author pt"><input type="number" value={d.author_pt} onChange={set("author_pt", Number)} /></Field>
          </div>
          <p className="muted small">Title size actually used: {L.title_pt} pt (auto-shrinks to fit).</p>
          <Field label="Back cover copy" hint={`${(d.back_copy || "").length} characters · short is best – it sits above the barcode box`}><textarea rows={7} value={d.back_copy} onChange={set("back_copy")} /></Field>
          <button className="btn btn-small" onClick={async () => {
            if ((d.back_copy || "").trim() && !confirm("Replace the back-cover text in this form with a draft built from your book?")) return;
            try { const r = await api.post(`/api/projects/${proj.project.id}/listing/draft`); setD({ ...d, back_copy: r.back_copy }); toast("info", "Back-cover text drafted – edit it, then save."); }
            catch (e: any) { toast("err", e.message); }
          }}>✎ Draft back-cover text</button>
          <Field label="Back copy pt"><input type="number" value={d.back_copy_pt} onChange={set("back_copy_pt", Number)} /></Field>
          <h2>Colors</h2>
          <div className="grid3">
            <Field label="Background"><input type="color" value={d.background} onChange={set("background")} /></Field>
            <Field label="Accent"><input type="color" value={d.accent} onChange={set("accent")} /></Field>
            <Field label="Title"><input type="color" value={d.title_color} onChange={set("title_color")} /></Field>
            <Field label="Text"><input type="color" value={d.text_color} onChange={set("text_color")} /></Field>
          </div>
          <p className="muted small">Colors are written as RGB. This app does not convert to CMYK; KDP's printer handles color conversion, so expect some shift in the printed proof.</p>
          <h2>Spine</h2>
          <label className="check">
            <input type="checkbox" checked={!!d.spine_text_enabled} disabled={!g.spine_text.eligible} onChange={set("spine_text_enabled")} />
            <span>Spine text {g.spine_text.eligible ? <Badge kind="ok">allowed</Badge> : <Badge>not available</Badge>}
              {!g.spine_text.eligible && <span className="muted small block">{g.spine_text.reasons.join(" ")}</span>}
            </span>
          </label>
          {d.spine_text_enabled && <Field label="Spine text"><input value={d.spine_text || ""} onChange={set("spine_text")} /></Field>}
          <ErrorBox error={err} />
          <button className="btn btn-primary" disabled={saving} onClick={() => save()}>{saving ? "Saving…" : "Save & update preview"}</button>
        </section>
        <section className="card form-grid">
          <h2>Artwork</h2>
          <Field label="Front cover art" help="Use a colored version of one of your interior illustrations (Make colored version) or upload cover art in the Artwork library.">
            <select value={d.front_art_version_id || ""} onChange={(e) => save({ front_art_version_id: e.target.value || null })}>
              <option value="">— none —</option>
              {coverArt.map((a: any) => <option key={a.id} value={a.current_version_id}>{a.display_name}</option>)}
            </select>
          </Field>
          <Field label="Make a colored version of an interior illustration">
            <select defaultValue="" onChange={async (e) => { if (!e.target.value) return; const a = await api.post(`/api/versions/${e.target.value}/cover-art`); await assets.reload(); save({ front_art_version_id: a.current_version_id }); toast("ok", "Colored cover art created (simple region fill)."); }}>
              <option value="">Choose illustration…</option>
              {interior.map((a: any) => <option key={a.id} value={a.current_version_id}>{a.display_name}</option>)}
            </select>
          </Field>
          <div className="grid3">
            <Field label="Art scale"><input type="number" step="0.05" min={0.3} max={1.5} value={d.art_scale} onChange={set("art_scale", Number)} /></Field>
            <Field label="Offset X (in)"><input type="number" step="0.05" value={d.art_offset_x} onChange={set("art_offset_x", Number)} /></Field>
            <Field label="Offset Y (in)"><input type="number" step="0.05" value={d.art_offset_y} onChange={set("art_offset_y", Number)} /></Field>
          </div>
          <Field label="Back cover illustration (replaces the sample-page thumbnails)">
            <select value={d.back_art_version_id || ""} onChange={(e) => save({ back_art_version_id: e.target.value || null })}>
              <option value="">— none (use sample pages below) —</option>
              {coverArt.map((a: any) => <option key={a.id} value={a.current_version_id}>{a.display_name}</option>)}
            </select>
          </Field>
          <p className="small muted">Write front- and back-cover descriptions and generate the art on <a href={`#/p/${pid}/descriptions`}>✎ Page descriptions</a>.</p>
          <Field label="Back cover sample pages (up to 4)">
            <select multiple size={5} value={d.back_thumbnail_version_ids || []} onChange={(e) => setD({ ...d, back_thumbnail_version_ids: Array.from(e.target.selectedOptions).map((o) => o.value).slice(0, 4) })}>
              {interior.map((a: any) => <option key={a.id} value={a.current_version_id}>{a.display_name}</option>)}
            </select>
          </Field>
          <h2>Official KDP template overlay</h2>
          <p className="muted small">Download the template for your exact trim, paper and page count from KDP's cover calculator (kdp.amazon.com/cover-calculator), then upload its PNG in Artwork as “KDP cover template”. It is shown for alignment only and never printed.</p>
          <Field label="Template">
            <select value={d.template_overlay_version_id || ""} onChange={(e) => save({ template_overlay_version_id: e.target.value || null })}>
              <option value="">— none —</option>
              {templates.map((a: any) => <option key={a.id} value={a.current_version_id}>{a.display_name}</option>)}
            </select>
          </Field>
          <Field label={`Template opacity ${d.template_opacity}`}><input type="range" min={0.1} max={1} step={0.05} value={d.template_opacity} onChange={set("template_opacity", Number)} /></Field>
          <h2>Thumbnail check</h2>
          <p className="muted small">How the front cover reads at small sizes on a product page:</p>
          <div className="thumb-check">
            {[160, 90].map((w) => (
              <div key={w} className="thumb-crop" style={{ width: w, height: w * 11 / 8.5 }}>
                <img src={`/api/projects/${pid}/cover/preview.png?dpi=45&t=${stamp}`} alt={`Front cover at ${w}px`}
                  style={{ width: `${(g.full_width_in / (g.front.w + g.bleed_in)) * 100}%`, marginLeft: `-${(g.front.x / (g.front.w + g.bleed_in)) * 100}%`, marginTop: `-${(g.bleed_in / g.front.h) * (w * 11 / 8.5)}px` }} />
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="card">
        <h2>Geometry</h2>
        <dl className="facts">
          <dt>Interior pages used</dt><dd>{g.page_count}</dd>
          <dt>Spine</dt><dd>{g.page_count} × {g.spine_coefficient_in} in = <strong>{g.spine_width_in} in</strong></dd>
          <dt>Full cover</dt><dd><strong>{g.full_width_in} × {g.full_height_in} in</strong> ({g.full_width_pt} × {g.full_height_pt} pt)</dd>
          <dt>Formula</dt><dd>width = 2 × trim width + spine + 2 × {g.bleed_in} in bleed; height = trim height + 2 × {g.bleed_in} in</dd>
          <dt>Barcode reservation</dt><dd>{g.barcode.w} × {g.barcode.h} in, lower right of back cover, 0.25 in from trim and spine</dd>
          <dt>Profile</dt><dd>{g.profile_version}</dd>
        </dl>
        <h3>Rule conflicts we found</h3>
        <ul className="muted small">{g.conflicts.map((x: string) => <li key={x}>{x}</li>)}</ul>
      </section>
    </div>
  );
}
