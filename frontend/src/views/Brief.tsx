import React, { useRef, useState } from "react";
import { api } from "../api";
import { go } from "../App";
import { Badge, ErrorBox, Loading, Modal, useToast } from "../ui";

/** Choose a .md or .json book brief, preview what was found, then create a new book or apply it to an existing one. */
export function BriefImport({ pid, onApplied, label }: { pid?: string; onApplied?: () => void; label?: string }) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<any>(null);
  const [result, setResult] = useState<any>(null);

  async function choose(f: File | undefined) {
    if (!f) return;
    setFile(f); setErr(null); setResult(null); setBusy("Reading your brief");
    const fd = new FormData();
    fd.append("file", f);
    try { setPreview(await api.upload("/api/brief/parse", fd)); } catch (e) { setErr(e); setPreview({ error: true }); }
    finally { setBusy(null); }
  }
  async function apply() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(pid ? "Applying your brief" : "Creating your book");
    try {
      const r = await api.upload(pid ? `/api/projects/${pid}/brief` : "/api/projects/from-brief", fd);
      setResult(r);
      toast("ok", pid ? "Brief applied." : "Book created from your brief.");
      onApplied?.();
      if (!pid) { setPreview(null); go(`/p/${r.project_id}/auto`); }
    } catch (e) { setErr(e); }
    finally { setBusy(null); }
  }
  const s = preview?.summary;
  return (
    <>
      <button className="btn" onClick={() => input.current?.click()}>{label || "Import book brief (.md or .json)…"}</button>
      <input ref={input} type="file" accept=".md,.markdown,.txt,.json,text/markdown,text/plain,application/json" hidden onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />
      {preview && (
        <Modal title={pid ? "Apply book brief to this book" : "Create a book from your brief"} onClose={() => { setPreview(null); setResult(null); }}>
          {busy && <Loading what={busy} />}
          <ErrorBox error={err} />
          {s && !result && (
            <>
              <p className="muted small">From <strong>{file?.name}</strong>. Check what was found:</p>
              <dl className="facts">
                <dt>Read as</dt><dd>{s.format === "json" ? "JSON" : "Markdown"}</dd>
                <dt>Title</dt><dd>{s.title || <span className="warn-text">not found</span>}</dd>
                <dt>Author</dt><dd>{s.author || "–"}</dd>
                <dt>Audience</dt><dd>{s.audience || "–"}</dd>
                <dt>Book description</dt><dd>{s.has_book_description ? `${s.book_description_words.toLocaleString()} words` : "–"}</dd>
                <dt>Master style</dt><dd>{s.has_master_style ? "yes" : "–"}</dd>
                <dt>Characters</dt><dd>{s.characters ? `${s.characters}: ${s.character_names.join(", ")}` : "–"}</dd>
                <dt>Illustration pages</dt><dd>{s.illustration_pages || "–"} ({s.described_pages} described)</dd>
                {s.acts?.length > 0 && <><dt>Story parts</dt><dd>{s.acts.join(" · ")}</dd></>}
                <dt>Intro pages</dt><dd>{s.intro_pages ? `${s.intro_pages}: ${s.intro_labels.join(", ")}` : "–"}
                  {s.intro_exact && <div className="small muted">These become the book's intro pages, in this order (they replace the default title, “belongs to”, color-test and copyright pages).</div>}</dd>
                <dt>Front / back cover</dt><dd>{s.has_front_cover ? "front ✓" : "front – (the AI designs one from the title and characters)"} · {s.has_back_cover ? "back ✓" : "back –"} · {s.has_back_cover_text ? "back text ✓" : "back text –"}</dd>
                <dt>Listing</dt><dd>{s.has_listing ? "yes" : "–"}</dd>
              </dl>
              {s.first_pages?.length > 0 && (
                <details className="small"><summary>First pages as read</summary>
                  <ol className="plain">{s.first_pages.map((t: string) => <li key={t}>{t}</li>)}{s.last_page && <><li>…</li><li>{s.last_page}</li></>}</ol>
                </details>
              )}
              {preview.warnings.length > 0 && <ul className="warn-list">{preview.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
              {pid && <p className="small note">Applying replaces this book's settings, descriptions, style, cover text and listing with the brief's. Pages that already have pictures keep them. A backup is saved first.</p>}
              <div className="row gap end">
                <button className="btn" onClick={() => setPreview(null)}>Cancel</button>
                <button className="btn btn-primary" disabled={!!busy} onClick={apply}>{pid ? "Apply brief" : "Create book"}</button>
              </div>
            </>
          )}
          {result && (
            <>
              <h3>Done</h3>
              <ul>{result.changes.map((c: string) => <li key={c}>{c}</li>)}</ul>
              {result.warnings.length > 0 && <ul className="warn-list">{result.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>}
              <div className="row gap end"><button className="btn btn-primary" onClick={() => { setPreview(null); setResult(null); }}>Close</button></div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}

export function BriefPanel({ pid, onApplied }: { pid: string; onApplied: () => void }) {
  return (
    <section className="card">
      <h2>Book brief (.md or .json) <Badge kind="info">fastest</Badge></h2>
      <p className="small muted">
        Put everything in one Markdown (or JSON) file – settings, book description, master style, characters, front/back cover, intro pages, every
        page's description and the Amazon listing – and load it here. Then make one sample page and click <strong>Create everything</strong>.
      </p>
      <div className="row gap wrap">
        <a className="btn" href="/api/brief/template" download>Download template</a>
        <a className="btn btn-ghost" href="/api/brief/template.json" download>JSON template</a>
        <BriefImport pid={pid} onApplied={onApplied} label="Load a brief into this book…" />
        <a className="btn btn-ghost" href={`/api/projects/${pid}/brief.md`} download>Save this book as a brief</a>
        <a className="btn btn-ghost" href={`/api/projects/${pid}/brief.json`} download>…as JSON</a>
      </div>
    </section>
  );
}
