import React, { useContext, useEffect, useRef, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Loading, useAsync, useToast } from "../ui";
import { IpWarning } from "./Heroes";
import { StoryPages } from "./StoryPages";

const MAX = 4000;

export default function PageDescriptions() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const rows = useAsync(() => api.get(`/api/projects/${pid}/page-descriptions`), [pid]);
  const toast = useToast();
  const [bulk, setBulk] = useState("");
  const [showBulk, setShowBulk] = useState(false);
  const [err, setErr] = useState<any>(null);

  const filled = (rows.data || []).filter((r: any) => r.description).length;
  async function fillAll() {
    const existing = (rows.data || []).filter((r: any) => r.description).length;
    if (existing && !confirm(`This replaces the descriptions of the first pages in order (${existing} page(s) already have one). Continue?`)) return;
    try {
      const r = await api.post(`/api/projects/${pid}/page-descriptions/bulk`, { text: bulk, add_pages: true });
      rows.setData(r.rows);
      await refresh();
      toast("ok", `Filled ${r.filled} page(s)${r.pages_added ? `, added ${r.pages_added} new illustration page(s)` : ""}.`);
      setBulk(""); setShowBulk(false);
    } catch (e) { setErr(e); }
  }

  return (
    <div className="page">
      <h1>Page descriptions</h1>
      <p className="lede">
        Describe exactly what each illustration should show. When a page has a description, it becomes that page's main instruction to the image
        generator (your book description and master style are still added). Pages left empty use the automatic plan.
      </p>
      <div className="row gap wrap">
        <Badge kind={filled === (rows.data || []).length && filled ? "ok" : "neutral"}>{filled} / {(rows.data || []).length} pages described</Badge>
        <button className="btn btn-small" onClick={() => setShowBulk(!showBulk)}>{showBulk ? "Close" : "Paste all descriptions at once…"}</button>
        <a className="btn btn-small" href={`#/p/${pid}/auto`}>Go to Create with AI →</a>
      </div>
      {showBulk && (
        <section className="card form-grid">
          <h2>Paste all descriptions</h2>
          <p className="small muted">Put a <strong>blank line between pages</strong>. Labels like “Page 3:” at the start are removed. If you paste more descriptions than there are pages, new illustration pages are added.</p>
          <textarea rows={12} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder={"Page 1: A fox reading under a mushroom, surrounded by ferns…\n\nPage 2: An owl in an oak tree at night, moon behind…"} />
          <span className="small muted">{bulk.split(/\n\s*\n/).filter((c) => c.trim()).length} page description(s) detected</span>
          <IpWarning text={bulk} />
          <ErrorBox error={err} />
          <button className="btn btn-primary" disabled={!bulk.trim()} onClick={fillAll}>Fill pages</button>
        </section>
      )}
      <h2 className="section-h">Covers</h2>
      <CoverDescription pid={pid} which="front" />
      <CoverDescription pid={pid} which="back" />
      <h2 className="section-h">Introductory pages</h2>
      <IntroDescriptions pid={pid} />
      <h2 className="section-h">Illustration pages</h2>
      {rows.loading && !rows.data && <Loading what="Loading pages" />}
      <ErrorBox error={rows.error} retry={rows.reload} />
      <div className="desc-list">
        {(rows.data || []).map((r: any) => <DescRow key={r.page_id} row={r} pid={pid} onChanged={rows.reload} />)}
      </div>
      {rows.data && rows.data.length === 0 && <p className="muted">This book has no illustration pages yet. Add some in Pages & layout or plan the book in Create with AI.</p>}
      <h2 className="section-h" id="stories">Story pages</h2>
      <StoryPages pid={pid} onSpecChanged={refresh} />
    </div>
  );
}

function DescRow({ row, pid, onChanged }: { row: any; pid: string; onChanged: () => void }) {
  const toast = useToast();
  const [text, setText] = useState<string>(row.description || "");
  const [state, setState] = useState<"saved" | "unsaved" | "saving" | "error">("saved");
  const [msg, setMsg] = useState("");
  const last = useRef(row.description || "");
  useEffect(() => { setText(row.description || ""); last.current = row.description || ""; setState("saved"); }, [row.page_id, row.description]);
  async function save() {
    if (text === last.current) { setState("saved"); return; }
    setState("saving");
    try {
      await api.put(`/api/pages/${row.page_id}/description`, { description: text });
      last.current = text; setState("saved"); setMsg("");
    } catch (e: any) { setState("error"); setMsg(e.message); }
  }
  useEffect(() => {
    if (text === last.current) return;
    setState("unsaved");
    const t = setTimeout(save, 1200);
    return () => clearTimeout(t);
  }, [text]);
  return (
    <div className="card desc-row">
      <div className="desc-thumb">
        {row.version_id ? <img src={img(row.version_id, 260)} alt={`Current picture for illustration ${row.illustration_number}`} /> : <span className="muted small">no picture yet</span>}
      </div>
      <div className="desc-main">
        <div className="row between wrap">
          <strong>Illustration {row.illustration_number} <span className="muted small">· book page {row.page_number}</span></strong>
          <span className="row gap">
            {row.approved && <Badge kind="ok">approved</Badge>}
            <span className={`save save-${state}`}>{state === "saved" ? "✓ Saved" : state === "saving" ? "Saving…" : state === "unsaved" ? "Unsaved" : "⚠ Not saved"}</span>
          </span>
        </div>
        <label className="sr-only" htmlFor={`d-${row.page_id}`}>Description for illustration {row.illustration_number}</label>
        <textarea id={`d-${row.page_id}`} rows={5} maxLength={MAX} value={text} onChange={(e) => setText(e.target.value)} onBlur={save}
          placeholder={row.draft_summary ? `Automatic plan (used if you leave this empty): ${row.draft_summary}` : "Describe what this illustration should show…"} />
        <div className="row between wrap">
          <span className={`small ${text.length > MAX - 200 ? "warn-text" : "muted"}`}>{text.length} / {MAX} characters</span>
          {state === "error" && <span className="warn-text small">{msg}</span>}
          {row.version_id && !row.approved && (
            <button className="btn btn-tiny" onClick={async () => {
              await save();
              if (!confirm("Generate a new picture for this page from its description? This is billed by OpenAI.")) return;
              try { await api.post(`/api/pages/${row.page_id}/regenerate`, { settings: {}, confirm: true }); toast("info", "Regenerating – see Create with AI for progress."); setTimeout(onChanged, 4000); }
              catch (e: any) { toast("err", e.message); }
            }}>Regenerate this page</button>
          )}
        </div>
        <IpWarning text={text} />
      </div>
    </div>
  );
}


function useAutosave(initial: string, saveFn: (v: string) => Promise<any>) {
  const [text, setText] = useState<string>(initial || "");
  const [state, setState] = useState<"saved" | "unsaved" | "saving" | "error">("saved");
  const [msg, setMsg] = useState("");
  const last = useRef(initial || "");
  useEffect(() => { setText(initial || ""); last.current = initial || ""; setState("saved"); }, [initial]);
  async function save() {
    if (text === last.current) { setState("saved"); return; }
    setState("saving");
    try { await saveFn(text); last.current = text; setState("saved"); setMsg(""); }
    catch (e: any) { setState("error"); setMsg(e.message); }
  }
  useEffect(() => {
    if (text === last.current) return;
    setState("unsaved");
    const t = setTimeout(save, 1200);
    return () => clearTimeout(t);
  }, [text]);
  return { text, setText, state, msg, save };
}

function SaveBadge({ state }: { state: string }) {
  return <span className={`save save-${state}`}>{state === "saved" ? "✓ Saved" : state === "saving" ? "Saving…" : state === "unsaved" ? "Unsaved" : "⚠ Not saved"}</span>;
}

function CoverDescription({ pid, which }: { pid: string; which: "front" | "back" }) {
  const { proj, refresh } = useContext(ProjectCtx);
  const toast = useToast();
  const key = `${which}_description`;
  const artKey = `${which}_art_version_id`;
  const data = proj.cover.data;
  const a = useAutosave(data[key] || "", (v) => api.put(`/api/projects/${pid}/cover`, { [key]: v }));
  const art = data[artKey];
  return (
    <div className="card desc-row">
      <div className="desc-thumb cover-thumb">
        {art ? <img src={img(art, 300)} alt={`Current ${which} cover art`} /> : <span className="muted small">no {which} cover art yet</span>}
      </div>
      <div className="desc-main">
        <div className="row between wrap">
          <strong>{which === "front" ? "Front cover" : "Back cover"}</strong>
          <SaveBadge state={a.state} />
        </div>
        <label className="sr-only" htmlFor={`cov-${which}`}>{which} cover description</label>
        <textarea id={`cov-${which}`} rows={4} maxLength={MAX} value={a.text} onChange={(e) => a.setText(e.target.value)} onBlur={a.save}
          placeholder={which === "front"
            ? "What the front-cover picture should show (the title, subtitle and author are added by the cover designer)…"
            : "What the back-cover picture should show – it goes below your back-cover text and above the barcode box…"} />
        <div className="row between wrap">
          <span className="small muted">{a.text.length} / {MAX} characters · color illustration, no text (the app adds all lettering)</span>
          {a.state === "error" && <span className="warn-text small">{a.msg}</span>}
          <span className="row gap">
            {which === "back" && art && <button className="btn btn-tiny btn-ghost" onClick={async () => { await api.put(`/api/projects/${pid}/cover`, { back_art_version_id: null }); refresh(); }}>Remove back art</button>}
            <button className="btn btn-tiny" onClick={async () => {
              await a.save();
              try {
                const est = await api.post(`/api/projects/${pid}/autobook/cover`, { which });
                if (!est.allowed) { toast("err", est.problems.join(" ")); return; }
                if (!confirm(`Generate ${which} cover art? Estimated cost: ${est.estimated_cost}.`)) return;
                await api.post(`/api/projects/${pid}/autobook/cover`, { which, confirm: true });
                toast("info", `Generating ${which} cover art – it appears here and in the Cover designer when done.`);
                setTimeout(refresh, 5000);
              } catch (e: any) { toast("err", e.message); }
            }}>{art ? "Regenerate" : "Generate"} {which} cover art</button>
          </span>
        </div>
        <IpWarning text={a.text} />
      </div>
    </div>
  );
}

function IntroDescriptions({ pid }: { pid: string }) {
  const rows = useAsync(() => api.get(`/api/projects/${pid}/intro-descriptions`), [pid]);
  if (rows.loading && !rows.data) return <Loading what="Loading intro pages" />;
  if (rows.data && rows.data.length === 0) return <p className="muted">This book has no introductory pages. Add them in Pages & layout.</p>;
  return (
    <div className="desc-list">
      <p className="small muted">The page text (title, “This book belongs to”, copyright…) stays as it is. The illustration goes into the empty space on the page, as a decorative frame behind the text, or – for picture pages such as a crew lineup or map – as a full-page picture. Edit the text itself in Pages & layout.</p>
      {(rows.data || []).map((r: any) => <IntroRow key={r.page_id} row={r} onChanged={rows.reload} />)}
    </div>
  );
}

function IntroRow({ row, onChanged }: { row: any; onChanged: () => void }) {
  const toast = useToast();
  const [placement, setPlacement] = useState<string>(row.placement || "free_space");
  const a = useAutosave(row.description || "", (v) => api.put(`/api/pages/${row.page_id}/intro-description`, { description: v, placement }));
  return (
    <div className="card desc-row">
      <div className="desc-thumb">
        {row.version_id ? <img src={img(row.version_id, 260)} alt={`Current art for ${row.label}`} /> : <span className="muted small">no illustration yet</span>}
      </div>
      <div className="desc-main">
        <div className="row between wrap">
          <strong>{row.label} <span className="muted small">· book page {row.page_number}</span></strong>
          <SaveBadge state={a.state} />
        </div>
        {row.page_text && <span className="small muted">Page text: “{row.page_text}”</span>}
        <label className="sr-only" htmlFor={`intro-${row.page_id}`}>Description for {row.label}</label>
        <textarea id={`intro-${row.page_id}`} rows={3} maxLength={MAX} value={a.text} onChange={(e) => a.setText(e.target.value)} onBlur={a.save}
          placeholder="e.g. A banner of seashells and starfish with the turtle waving…" />
        <div className="row between wrap">
          <select aria-label={`Placement for ${row.label}`} value={placement} onChange={async (e) => {
            setPlacement(e.target.value);
            await api.put(`/api/pages/${row.page_id}/intro-description`, { description: a.text, placement: e.target.value });
          }}>
            <option value="free_space">Put it in the empty space next to the text</option>
            <option value="behind_text">Full-page frame behind the text</option>
            <option value="full_page">Full-page picture (no app text)</option>
          </select>
          <button className="btn btn-tiny" disabled={!a.text.trim()} onClick={async () => {
            await a.save();
            try {
              const est = await api.post(`/api/pages/${row.page_id}/generate-intro`, {});
              if (!est.allowed) { toast("err", est.problems.join(" ")); return; }
              if (!confirm(`Generate an illustration for “${row.label}”? Estimated cost: ${est.estimated_cost}.`)) return;
              await api.post(`/api/pages/${row.page_id}/generate-intro`, { confirm: true });
              toast("info", "Generating – it appears here when done.");
              setTimeout(onChanged, 5000);
            } catch (e: any) { toast("err", e.message); }
          }}>{row.version_id ? "Regenerate" : "Generate"} illustration</button>
        </div>
        {a.state === "error" && <span className="warn-text small">{a.msg}</span>}
        <IpWarning text={a.text} />
      </div>
    </div>
  );
}
