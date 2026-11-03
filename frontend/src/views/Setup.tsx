import React, { useContext, useEffect, useState } from "react";
import { api, fmtIn } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Field, useToast } from "../ui";

export default function Setup() {
  const { proj, refresh } = useContext(ProjectCtx);
  const [spec, setSpec] = useState<any>(proj.spec);
  const [name, setName] = useState(proj.project.name);
  const [err, setErr] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  useEffect(() => setSpec(proj.spec), [proj.spec]);
  const set = (k: string, conv: (v: any) => any = (v) => v) => (e: any) =>
    setSpec({ ...spec, [k]: e.target.type === "checkbox" ? e.target.checked : conv(e.target.value) });

  async function save(e?: React.FormEvent) {
    e?.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      await api.put(`/api/projects/${proj.project.id}/spec`, spec);
      if (name !== proj.project.name) await api.patch(`/api/projects/${proj.project.id}`, { name });
      await refresh();
      toast("ok", "Book setup saved.");
    } catch (e) {
      setErr(e);
    } finally {
      setSaving(false);
    }
  }
  const asm = proj.assembly;
  const ill = asm.illustration_count;
  const geo = asm.geometry?.recto;

  return (
    <div className="page">
      <h1>Book setup</h1>
      <p className="lede">The basic facts about your book. Print settings decide page size, margins and the cover size.</p>
      <div className="split">
        <form className="card form-grid" onSubmit={save}>
          <h2>About the book</h2>
          <Field label="Project name (only shown in this app)"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Title"><input value={spec.title} onChange={set("title")} /></Field>
          <Field label="Subtitle"><input value={spec.subtitle || ""} onChange={set("subtitle")} /></Field>
          <Field label="Author / pen name"><input value={spec.author || ""} onChange={set("author")} /></Field>
          <Field label="Audience"><input value={spec.audience || ""} onChange={set("audience")} /></Field>
          <div className="row gap">
            <Field label="Min age"><input type="number" value={spec.age_min} onChange={set("age_min", Number)} /></Field>
            <Field label="Max age"><input type="number" value={spec.age_max} onChange={set("age_max", Number)} /></Field>
          </div>
          <Field label="Theme / book description" hint={`${((spec.theme || "").trim() ? (spec.theme || "").trim().split(/\s+/).length : 0).toLocaleString()} / 10,000 words`}><textarea rows={8} maxLength={90000} value={spec.theme || ""} onChange={set("theme")} /></Field>
          <Field label="Drawing difficulty"><input value={spec.difficulty || ""} onChange={set("difficulty")} /></Field>
          <Field label="Language"><input value={spec.language} onChange={set("language")} /></Field>
          <h2>Print settings</h2>
          <Field label="Binding"><select value={spec.binding} disabled><option value="paperback">Paperback</option></select></Field>
          <Field label="Trim size" help="The final page size after cutting. Only validated presets are offered.">
            <select value={spec.trim} onChange={set("trim")}>
              <option value="8.5x11">8.5 × 11 in</option>
              <option value="8x10">8 × 10 in</option>
              <option value="8.5x8.5">8.5 × 8.5 in</option>
            </select>
          </Field>
          <Field label="Ink & paper" help="Coloring books normally use black ink on white paper. Paper thickness changes the spine width.">
            <select value={spec.paper} onChange={set("paper")}>
              <option value="bw_white">Black ink on white paper</option>
              <option value="bw_cream">Black ink on cream paper</option>
            </select>
          </Field>
          <label className="check">
            <input type="checkbox" checked={!!spec.interior_bleed} onChange={set("interior_bleed")} />
            <span>
              Interior bleed <Badge>{spec.interior_bleed ? "on" : "off (default)"}</Badge>
              <span className="muted small block">Bleed means artwork printed to the very edge. Pages get 0.125 in wider and 0.25 in taller, and margins grow. Most coloring books don't need it.</span>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={!!spec.blank_backs} onChange={set("blank_backs")} />
            <span>
              Blank back after every illustration
              <span className="muted small block">Reduces marker bleed-through. Blank pages still count toward printing cost and spine width.</span>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={!!spec.facing_text} onChange={set("facing_text")} />
            <span>
              Story text on the left page, facing each picture
              <span className="muted small block">Each picture stays on a right-hand page; the left page facing it holds a story describing it (write it on ✎ Page descriptions, or let AI write it). The story sits on the back of the previous picture instead of a blank page.</span>
            </span>
          </label>
          {spec.facing_text && (
            <label className="block small">Words per story page{" "}
              <input type="number" min={50} max={900} step={10} value={spec.story_words ?? 400} onChange={set("story_words", Number)} style={{ width: "6rem" }} />
            </label>
          )}
          <Field label="Safe margin (inches)" help="Keep artwork and text at least this far from the page edges. KDP's own minimum depends on page count; the larger value is used.">
            <input type="number" step="0.05" min={0.25} max={1.5} value={spec.safe_margin_in} onChange={set("safe_margin_in", Number)} />
          </Field>
          <div className="row gap">
            <Field label="Planned illustrations"><input type="number" min={1} max={300} value={spec.illustration_count} onChange={set("illustration_count", Number)} /></Field>
            <Field label="Intro pages (plan)"><input type="number" min={0} max={20} value={spec.intro_pages} onChange={set("intro_pages", Number)} /></Field>
          </div>
          <Field label="Cover finish"><select value={spec.cover_finish} onChange={set("cover_finish")}><option value="matte">Matte</option><option value="glossy">Glossy</option></select></Field>
          <ErrorBox error={err} />
          <div className="row gap">
            <button className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save setup"}</button>
            {ill < spec.illustration_count && (
              <button type="button" className="btn" onClick={async () => { const r = await api.post(`/api/projects/${proj.project.id}/spec/apply-slots`); await refresh(); toast("ok", `Added ${r.added} empty illustration pages.`); }}>
                Add {spec.illustration_count - ill} empty illustration pages
              </button>
            )}
          </div>
        </form>
        <aside className="card">
          <h2>Current layout</h2>
          <dl className="facts">
            <dt>Interior pages</dt><dd>{asm.page_count}</dd>
            <dt>Illustrations</dt><dd>{ill}</dd>
            <dt>Intro pages</dt><dd>{asm.intro_count}</dd>
            <dt>Blank pages</dt><dd>{asm.blank_count}</dd>
            <dt>PDF page size</dt><dd>{geo ? `${geo.media_w} × ${geo.media_h} in (${geo.media_w_pt} × ${geo.media_h_pt} pt)` : "–"}</dd>
            <dt>Margins used</dt><dd>{geo ? `${fmtIn(geo.inside_margin)} inside · ${fmtIn(geo.outside_margin)} outside` : "–"}</dd>
            <dt>Spine width</dt><dd>{proj.cover.geometry.spine_width_in} in</dd>
            <dt>Full cover</dt><dd>{proj.cover.geometry.full_width_in} × {proj.cover.geometry.full_height_in} in</dd>
          </dl>
          {asm.parity_notes.map((n: string) => <p key={n} className="note">{n}</p>)}
          <div className="card-inner">
            <h2>Next book in this series</h2>
            <p className="muted small">Starts a new book with the same size, ages, drawing style, master style, characters, intro pages (with their descriptions) and cover colors. The story, page descriptions, artwork and back-cover text start empty.</p>
            <button type="button" className="btn" onClick={async () => {
              try {
                const r = await api.post(`/api/projects/${proj.project.id}/series/next`, {});
                toast("ok", `Created “${r.title}”. Describe its story and pages next.`);
                window.location.hash = `#/p/${r.project_id}/auto`;
              } catch (e: any) { toast("err", e.message); }
            }}>Start the next book…</button>
          </div>
          <div className="danger-zone">
            <h2>Delete this book</h2>
            <p className="muted small">Removes the book and its pages, artwork and exports from the app. A backup copy (.cbsproj) is saved in the app's data folder first, so it can be restored with “Import project…”.</p>
            <button type="button" className="btn btn-danger" onClick={async () => {
              const typed = prompt(`To delete “${proj.project.name}”, type DELETE below.`);
              if (typed !== "DELETE") { if (typed !== null) toast("info", "Not deleted – you need to type DELETE."); return; }
              try { await api.del(`/api/projects/${proj.project.id}`); toast("ok", "Book deleted. A backup was saved in the data folder."); window.location.hash = "#/"; }
              catch (e: any) { toast("err", e.message); }
            }}>Delete book…</button>
          </div>
          <p className="muted small">Print rules come from a dated KDP profile ({proj.cover.geometry.profile_version}). Always compare with KDP's own cover calculator before uploading.</p>
        </aside>
      </div>
    </div>
  );
}
