import React, { useEffect, useRef, useState } from "react";
import { api, img } from "../api";
import { Badge, ErrorBox, Loading, Modal, useAsync, useToast } from "../ui";
import { IpWarning } from "./Heroes";

const words = (t: string) => (t.match(/[A-Za-z0-9’']+/g) || []).length;

/** Story text printed on the left page facing each picture. */
export function StoryPages({ pid, onSpecChanged }: { pid: string; onSpecChanged: () => void }) {
  const data = useAsync(() => api.get(`/api/projects/${pid}/stories`), [pid]);
  const toast = useToast();
  const [showBulk, setShowBulk] = useState(false);
  const [bulk, setBulk] = useState("");
  const [err, setErr] = useState<any>(null);
  const [ask, setAsk] = useState<any>(null);
  const [job, setJob] = useState<any>(null);
  const poll = useRef<any>(null);
  useEffect(() => () => clearInterval(poll.current), []);
  if (data.loading && !data.data) return <Loading what="Loading story pages" />;
  if (!data.data) return <ErrorBox error={data.error} retry={data.reload} />;
  const d = data.data;
  if (!d.facing_text) {
    return (
      <section className="card">
        <h2>Story text on the left page <Badge kind="info">optional</Badge></h2>
        <p className="small">Turn this on to print a story page – about {d.story_words} words describing the picture – on the left page facing every
          illustration. The story for each picture is printed on the back of the picture before it, so the book gets only about 2 extra pages.</p>
        <button className="btn btn-primary" onClick={async () => { await api.put(`/api/projects/${pid}/spec`, { facing_text: true }); data.reload(); onSpecChanged(); toast("ok", "Story pages turned on."); }}>Turn on story pages</button>
      </section>
    );
  }
  const rows = d.rows;
  const filled = rows.filter((r: any) => r.text.trim()).length;
  const missing = rows.length - filled;
  async function estimate(overwrite = false) {
    try { setAsk({ ...(await api.post(`/api/projects/${pid}/stories/estimate`, { overwrite })), overwrite }); } catch (e: any) { toast("err", e.message); }
  }
  async function write() {
    try {
      const j = await api.post(`/api/projects/${pid}/stories/write`, { confirm: true, overwrite: ask.overwrite });
      setAsk(null); setJob(j);
      poll.current = setInterval(async () => {
        const s = await api.get(`/api/jobs/${j.id}`);
        setJob(s); data.reload();
        if (!["queued", "running"].includes(s.status)) {
          clearInterval(poll.current);
          const r = s.result || {};
          toast(s.status === "succeeded" ? "ok" : "err", s.status === "succeeded"
            ? `Wrote ${(r.written || []).length} story page(s)${(r.failed || []).length ? `; ${(r.failed || []).length} failed` : ""}${r.stopped_at_limit ? " – stopped at your spending limit" : ""}.`
            : `Story writing ${s.status}: ${s.error || ""}`);
          onSpecChanged();
        }
      }, 2000);
    } catch (e: any) { toast("err", e.message); }
  }
  return (
    <section className="card">
      <div className="row between wrap">
        <h2>Story text on the left page</h2>
        <div className="row gap wrap">
          <Badge kind={missing ? "neutral" : "ok"}>{filled} / {rows.length} stories written</Badge>
          <button className="btn btn-small" onClick={() => setShowBulk(!showBulk)}>{showBulk ? "Close" : "Paste all stories…"}</button>
          <button className="btn btn-small btn-primary" disabled={!missing || (job && ["queued", "running"].includes(job.status))} onClick={() => estimate(false)}>✨ Write {missing} missing with AI…</button>
          <button className="btn btn-small btn-ghost" onClick={async () => { if (!confirm("Turn off story pages? The text is kept and comes back if you turn them on again.")) return; await api.put(`/api/projects/${pid}/spec`, { facing_text: false }); data.reload(); onSpecChanged(); }}>Turn off</button>
        </div>
      </div>
      <p className="small muted">Each story is printed on the left page facing its picture. Target: <strong>{d.story_words} words</strong> per page
        (change it in Book setup). The text is sized to fit, from 16 pt down to 10 pt.</p>
      {job && ["queued", "running"].includes(job.status) && <p className="note" role="status">Writing stories… {Math.round((job.progress || 0) * 100)}% {job.progress_label || ""}</p>}
      {showBulk && (
        <div className="form-grid">
          <p className="small muted">Start each story with a line like <code>Page 1</code> or <code>Page 1: Title</code>. Paragraphs inside a story are kept. (A line with <code>---</code> also separates stories.)</p>
          <textarea rows={12} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder={"Page 1: The Big Pull\nBarnaby grabbed the rope…\n\nPippa giggled…\n\nPage 2: The Wind Cloud\n…"} />
          <IpWarning text={bulk} />
          <ErrorBox error={err} />
          <button className="btn btn-primary" disabled={!bulk.trim()} onClick={async () => {
            try { const r = await api.post(`/api/projects/${pid}/stories/bulk`, { text: bulk }); data.setData({ ...d, rows: r.rows }); setBulk(""); setShowBulk(false); toast("ok", `Filled ${r.filled} story page(s)${r.ignored ? `; ${r.ignored} had no matching picture` : ""}.`); }
            catch (e) { setErr(e); }
          }}>Fill story pages</button>
        </div>
      )}
      <div className="desc-list">
        {rows.map((r: any) => <StoryRow key={r.page_id} row={r} pid={pid} target={d.story_words} />)}
      </div>
      {ask && (
        <Modal title="Write story text with AI" onClose={() => setAsk(null)}>
          <p>OpenAI ({ask.model}) will write <strong>{ask.count}</strong> story page(s) of about {d.story_words} words, one after another so the story flows from page to page.</p>
          <p className="small">Estimated cost: <strong>{ask.estimated_cost}</strong> (from your per-story estimate) · your limit {ask.budget.spending_limit ?? "not set"}, estimated so far {ask.budget.estimated_spent}.</p>
          <p className="small muted">{ask.note} KDP asks whether text is AI-generated – the Listing page will be set to “AI-generated”.</p>
          {ask.problems.length > 0 && <ul className="warn-list small">{ask.problems.map((p: string) => <li key={p}>{p}</li>)}</ul>}
          <div className="row gap end">
            <button className="btn" onClick={() => setAsk(null)}>Cancel</button>
            <button className="btn btn-primary" disabled={!ask.allowed} onClick={write}>Write {ask.count} stories</button>
          </div>
        </Modal>
      )}
    </section>
  );
}

function StoryRow({ row, pid, target }: { row: any; pid: string; target: number }) {
  const toast = useToast();
  const [title, setTitle] = useState(row.title || "");
  const [text, setText] = useState(row.text || "");
  const [state, setState] = useState("saved");
  const [info, setInfo] = useState<any>(row);
  const [preview, setPreview] = useState(0);
  const last = useRef({ title: row.title || "", text: row.text || "" });
  useEffect(() => { setTitle(row.title || ""); setText(row.text || ""); last.current = { title: row.title || "", text: row.text || "" }; setInfo(row); }, [row.text, row.title]);
  async function save() {
    if (title === last.current.title && text === last.current.text) return;
    setState("saving");
    try { const r = await api.put(`/api/pages/${row.page_id}/story`, { title, text }); last.current = { title, text }; setInfo(r); setState("saved"); }
    catch (e: any) { setState("error"); toast("err", e.message); }
  }
  useEffect(() => {
    if (title === last.current.title && text === last.current.text) return;
    setState("unsaved");
    const t = setTimeout(save, 1200);
    return () => clearTimeout(t);
  }, [title, text]);
  const w = words(text);
  return (
    <div className="desc-row">
      <div className="desc-thumb">{row.version_id ? <img src={img(row.version_id, 160)} alt="" loading="lazy" /> : <span className="muted small">picture {row.illustration_number}</span>}</div>
      <div className="desc-body">
        <div className="row between wrap">
          <strong>Story for picture {row.illustration_number}</strong>
          <span className="small muted">left page {row.story_page_number ?? "–"} · picture on page {row.picture_page_number ?? "–"} <span className={`save save-${state}`}>{state === "saved" ? "✓ Saved" : state === "saving" ? "Saving…" : state === "unsaved" ? "Unsaved" : "⚠ Not saved"}</span></span>
        </div>
        {row.description && <p className="small muted clamp2">Picture: {row.description}</p>}
        <input aria-label={`Story title for picture ${row.illustration_number}`} placeholder="Title (optional)" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} onBlur={save} />
        <textarea aria-label={`Story text for picture ${row.illustration_number}`} rows={6} value={text} maxLength={9000} onChange={(e) => setText(e.target.value)} onBlur={save}
          placeholder={`About ${target} words describing what's happening in the picture. Leave a blank line between paragraphs.`} />
        <div className="row between wrap small">
          <span className={w && w < target * 0.9 ? "warn-text" : "muted"}>{w} / {target} words
            {info.fits === false && <span className="warn-text"> · too long to fit the page – shorten it</span>}
            {info.fits && info.font_pt && <span className="muted"> · prints at {info.font_pt} pt</span>}
            {info.ai && <> · <Badge kind="review">AI-written{info.edited_after_ai ? ", edited" : ""}</Badge></>}</span>
          <span className="row gap">
            {text.trim() && <button className="btn btn-tiny" onClick={async () => { await save(); setPreview(Date.now()); }}>Preview page</button>}
          </span>
        </div>
        <IpWarning text={title + " " + text} />
        {preview > 0 && <img className="story-preview" src={`/api/projects/${pid}/stories/${row.page_id}/preview.png?dpi=50&t=${preview}`} alt={`Preview of the story page for picture ${row.illustration_number}`} />}
      </div>
    </div>
  );
}
