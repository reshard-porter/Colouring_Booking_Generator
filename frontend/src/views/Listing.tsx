import React, { useContext, useEffect, useState } from "react";
import { api } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Field, useAsync, useToast } from "../ui";

export default function Listing() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const [l, setL] = useState<any>(proj.listing);
  const disc = useAsync(() => api.get(`/api/projects/${pid}/disclosure`), [pid]);
  const ip = useAsync(() => api.get(`/api/projects/${pid}/ip-check`), [pid]);
  const [lic, setLic] = useState<string>((proj.listing.licensed_terms || []).map((r: any) => `${r.term} | ${r.evidence}`).join("\n"));
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  useEffect(() => setL(proj.listing), [proj.listing]);
  const [checks, setChecks] = useState<any[]>([]);
  const [drafting, setDrafting] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => api.post("/api/listing/check", { title: l.title, subtitle: l.subtitle, description: l.description, keywords: l.keywords })
      .then((r) => setChecks(r.checks)).catch(() => setChecks([])), 300);
    return () => clearTimeout(t);
  }, [l.title, l.subtitle, l.description, (l.keywords || []).join("\n")]);
  async function draft() {
    if ((l.description || "").trim() && !confirm("Replace the description and keyword ideas in this form with a draft built from your book? (Nothing is saved until you click Save.)")) return;
    setDrafting(true);
    try {
      const d = await api.post(`/api/projects/${pid}/listing/draft`);
      setL({ ...l, description: d.description, keywords: d.keywords });
      toast("info", "Draft filled in from your book – read it, edit it, then click Save listing draft.");
    } catch (e: any) { toast("err", e.message); } finally { setDrafting(false); }
  }
  const tsLen = (l.title || "").length + (l.subtitle || "").length;
  const kwLines = (l.keywords || []).filter((k: string) => k.trim());
  const set = (k: string) => (e: any) => setL({ ...l, [k]: e.target.value });
  async function save() {
    try {
      const licensed_terms = lic.split("\n").map((ln) => ln.split("|")).filter((p) => p[0]?.trim()).map((p) => ({ term: p[0].trim().toLowerCase(), evidence: (p[1] || "").trim() }));
      await api.put(`/api/projects/${pid}/listing`, { ...l, licensed_terms });
      await refresh();
      disc.reload();
      ip.reload();
      toast("ok", "Listing draft saved.");
    } catch (e) {
      setErr(e);
    }
  }
  const asm = proj.assembly;
  return (
    <div className="page">
      <h1>Listing & disclosure</h1>
      <p className="lede">Draft what you will type into KDP. Nothing is sent to Amazon from here.</p>
      <div className="split">
        <section className="card form-grid">
          <Field label="Title"><input value={l.title} onChange={set("title")} /></Field>
          <Field label="Subtitle"><input value={l.subtitle} onChange={set("subtitle")} /></Field>
          <Field label="Author"><input value={l.author} onChange={set("author")} /></Field>
          <div className="grid2">
            <Field label="Language"><input value={l.language} onChange={set("language")} /></Field>
            <Field label="Age range"><input value={l.age_range} onChange={set("age_range")} /></Field>
          </div>
          <p className={`small ${tsLen > 200 ? "warn-text" : "muted"}`}>Title + subtitle: {tsLen} / 200 characters</p>
          <div className="grid2">
            <Field label="Series name (optional)"><input value={l.series_name || ""} onChange={set("series_name")} placeholder="e.g. Sprocket Squad" /></Field>
            <Field label="Number in series"><input value={l.series_number || ""} onChange={set("series_number")} placeholder="1" /></Field>
          </div>
          <div className="row between wrap">
            <strong>Description</strong>
            <button className="btn btn-small" disabled={drafting} onClick={draft}>{drafting ? "Drafting…" : "✎ Draft from my book"}</button>
          </div>
          <Field label="Description" hint={`Be accurate: ${asm.illustration_count} illustrations, ${proj.spec.trim.replace("x", " × ")} in. ${(l.description || "").length} / 4000 characters (KDP counts HTML tags too).`}>
            <textarea rows={12} value={l.description} onChange={set("description")} />
          </Field>
          <Field label="Keyword ideas (one per line, KDP allows 7 boxes)" hint={`${kwLines.length} / 7 boxes · longest ${Math.max(0, ...kwLines.map((k: string) => k.length))} / 50 characters`}>
            <textarea rows={7} value={(l.keywords || []).join("\n")} onChange={(e) => setL({ ...l, keywords: e.target.value.split("\n") })} />
          </Field>
          {checks.length > 0 && (
            <ul className="findings small" aria-live="polite">
              {checks.map((c: any, i: number) => <li key={i}><Badge kind={c.severity === "error" ? "bad" : c.severity === "warning" ? "warn" : "info"}>{c.severity}</Badge> {c.message}</li>)}
            </ul>
          )}
          <p className="small muted">Drafts and keyword ideas come only from your book's own details; they are not search or sales data. Check keywords with your own Amazon searches.</p>
          <Field label="Category research notes (your own)"><textarea rows={3} value={l.category_notes} onChange={set("category_notes")} /></Field>
          <Field label="Competitor notes (entered by you)"><textarea rows={3} value={l.competitor_notes} onChange={set("competitor_notes")} /></Field>
          <Field label="ISBN choice">
            <select value={l.isbn_choice} onChange={set("isbn_choice")}>
              <option value="undecided">Undecided</option>
              <option value="free_kdp">Free KDP ISBN</option>
              <option value="own">My own ISBN</option>
            </select>
          </Field>
          <Field label="ISBN notes"><input value={l.isbn_notes} onChange={set("isbn_notes")} /></Field>
          <div className="grid2">
            <Field label="Text: AI involvement">
              <select value={l.text_ai_involvement} onChange={set("text_ai_involvement")}>
                <option value="none">No AI</option><option value="ai_assisted">AI-assisted</option><option value="ai_generated">AI-generated</option>
              </select>
            </Field>
            <Field label="Translations: AI involvement">
              <select value={l.translation_ai_involvement} onChange={set("translation_ai_involvement")}>
                <option value="not_applicable">No translation</option><option value="none">Translated without AI</option><option value="ai_generated">AI-generated translation</option>
              </select>
            </Field>
          </div>
          <ErrorBox error={err} />
          <button className="btn btn-primary" onClick={save}>Save listing draft</button>
        </section>
        <aside className="card">
          <h2>Proposed AI disclosure</h2>
          {disc.data && (
            <>
              <p className="note">{disc.data.status}</p>
              <dl className="facts">
                <dt>Interior images</dt><dd>{disc.data.images.interior.proposed_answer}<span className="block small muted">{disc.data.images.interior.total} used · {disc.data.images.interior.ai_generated} AI-generated · {disc.data.images.interior.ai_assisted} AI-assisted · {disc.data.images.interior.unknown} unknown</span></dd>
                <dt>Cover images</dt><dd>{disc.data.images.cover.proposed_answer}</dd>
                <dt>Text</dt><dd>{disc.data.text.declared}</dd>
                <dt>Translations</dt><dd>{disc.data.translations.declared}</dd>
              </dl>
              <ul className="small">
                <li>{disc.data.definitions.ai_generated}</li>
                <li>{disc.data.definitions.ai_assisted}</li>
                <li>{disc.data.definitions.brainstorming_note}</li>
              </ul>
              <p className="small">Guideline: <a href={disc.data.source} target="_blank" rel="noreferrer">KDP content guidelines</a></p>
            </>
          )}
          <h2>Protected names check</h2>
          <p className="muted small">Scans titles, keywords, description, cover text, page text, scenes, characters and file names for well-known characters, teams and brands (Justice League, Marvel, popular anime, Disney…). A list-based check, not legal advice.</p>
          {ip.data && ip.data.hits.length === 0 && <p className="ok-text">No listed protected names found.</p>}
          {ip.data && ip.data.hits.length > 0 && (
            <ul className="findings">
              {ip.data.hits.map((h: any, i: number) => (
                <li key={i}><Badge kind={h.licensed ? "review" : h.severity === "error" ? "bad" : "warn"}>{h.licensed ? "licensed" : h.severity}</Badge> “{h.matched}” in {h.where} – {h.owner}</li>
              ))}
            </ul>
          )}
          <button className="btn btn-small" onClick={ip.reload}>Re-check</button>
          <Field label="Names you hold a license for (term | license evidence)" hint="Only use this if you actually have a written license that covers print books on Amazon. Matches then become review items instead of errors.">
            <textarea rows={3} value={lic} onChange={(e) => setLic(e.target.value)} placeholder="e.g. sunny bunny | License agreement #123 with Example Studio, 2026" />
          </Field>
          <h2>Low-content books & ISBNs</h2>
          <p className="small">KDP treats books like blank journals and planners with repetitive interiors as “low-content”; those can't use a free KDP ISBN. Coloring books with varied original illustrations are generally <em>not</em> low-content under current guidance, but the app doesn't classify your book for you – check KDP's help page and decide.</p>
          <p className="small muted">No AI output is guaranteed to be exclusive, copyrightable or automatically safe to sell. Prefer original characters and properly licensed material.</p>
        </aside>
      </div>
    </div>
  );
}
