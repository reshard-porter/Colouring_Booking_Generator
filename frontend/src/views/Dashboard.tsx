import React, { useState } from "react";
import { api } from "../api";
import { go } from "../App";
import { Badge, Empty, ErrorBox, Field, Loading, Modal, useAsync, useToast } from "../ui";
import { BriefImport } from "./Brief";

export default function Dashboard() {
  const { data, error, loading, reload } = useAsync(() => api.get("/api/projects"), []);
  const [creating, setCreating] = useState(false);
  const toast = useToast();

  async function importArchive(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const p = await api.upload("/api/projects/import", fd);
      toast("ok", "Project imported.");
      go(`/p/${p.project.id}/setup`);
    } catch (err: any) {
      toast("err", err.message);
    }
    e.target.value = "";
  }

  return (
    <div className="page">
      <div className="hero">
        <div>
          <h1>Your coloring books</h1>
          <p className="lede">
            Plan a book, import or create line art, lay out the pages, design a cover, check everything, and download a package to upload to Amazon KDP
            yourself.
          </p>
        </div>
        <div className="hero-actions">
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New book
          </button>
          <BriefImport />
          <a className="btn btn-ghost" href="/api/brief/template" download>Brief template</a>
          <label className="btn">
            Import project…
            <input type="file" accept=".cbsproj,.zip" hidden onChange={importArchive} />
          </label>
          <button className="btn" onClick={async () => { const p = await api.post("/api/projects/sample"); go(`/p/${p.project.id}/setup`); }}>
            Open sample
          </button>
        </div>
      </div>
      <ErrorBox error={error} retry={reload} />
      {loading && <Loading what="Loading projects" />}
      {data && data.length === 0 && (
        <Empty title="No books yet">
          <p>Start a new book or open the sample project to see the full workflow.</p>
        </Empty>
      )}
      <div className="cards">
        {(data || []).map((p: any) => (
          <a key={p.id} className="card project-card" href={`#/p/${p.id}/setup`}>
            <h3>{p.name}</h3>
            <p className="muted">{p.title}</p>
            <div className="row gap">
              <Badge>{p.page_count} pages</Badge>
              <Badge>{p.illustrations} illustrations</Badge>
              <Badge kind={p.approved === p.illustrations && p.illustrations ? "ok" : "neutral"}>
                {p.approved}/{p.illustrations} approved
              </Badge>
              {p.is_sample && <Badge kind="review">sample · demo art</Badge>}
            </div>
            <div className="row between">
              <p className="muted small">Updated {new Date(p.updated_at).toLocaleString()}</p>
              <button className="btn btn-tiny btn-danger" aria-label={`Delete ${p.name}`} onClick={async (e) => {
                e.preventDefault(); e.stopPropagation();
                const typed = prompt(`To delete “${p.name}”, type DELETE below.`);
                if (typed !== "DELETE") return;
                try { await api.del(`/api/projects/${p.id}`); toast("ok", "Book deleted. A backup was saved in the data folder."); reload(); }
                catch (err: any) { toast("err", err.message); }
              }}>Delete</button>
            </div>
          </a>
        ))}
      </div>
      {creating && <NewBook onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewBook({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({
    title: "", subtitle: "", author: "", audience: "Children ages 4–7", age_min: 4, age_max: 7,
    theme: "", difficulty: "Large enclosed shapes and bold outlines", illustration_count: 40, intro_pages: 4, trim: "8.5x11",
  });
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "number" ? +e.target.value : e.target.value });
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const p = await api.post("/api/projects", { name: f.title || "Untitled book", spec: { ...f, title: f.title || "Untitled book" } });
      go(`/p/${p.project.id}/plan`);
    } catch (e) {
      setErr(e);
      setBusy(false);
    }
  }
  return (
    <Modal title="New coloring book" onClose={onClose}>
      <form onSubmit={create} className="form-grid">
        <Field label="Working title"><input required value={f.title} onChange={set("title")} placeholder="e.g. Jungle Friends" /></Field>
        <Field label="Subtitle"><input value={f.subtitle} onChange={set("subtitle")} /></Field>
        <Field label="Author / pen name"><input value={f.author} onChange={set("author")} /></Field>
        <Field label="Audience"><input value={f.audience} onChange={set("audience")} /></Field>
        <div className="row gap">
          <Field label="Min age"><input type="number" min={1} max={99} value={f.age_min} onChange={set("age_min")} /></Field>
          <Field label="Max age"><input type="number" min={1} max={99} value={f.age_max} onChange={set("age_max")} /></Field>
        </div>
        <Field label="Theme"><input value={f.theme} onChange={set("theme")} placeholder="Original characters doing…" /></Field>
        <Field label="Drawing difficulty"><input value={f.difficulty} onChange={set("difficulty")} /></Field>
        <div className="row gap">
          <Field label="Illustrations"><input type="number" min={1} max={200} value={f.illustration_count} onChange={set("illustration_count")} /></Field>
          <Field label="Intro pages" help="Title page, 'this book belongs to', color test, copyright… They come before the illustrations."><input type="number" min={0} max={20} value={f.intro_pages} onChange={set("intro_pages")} /></Field>
        </div>
        <Field label="Trim size" help="The final page size after the printer cuts the paper. 8.5 × 11 in is the most common coloring-book size.">
          <select value={f.trim} onChange={set("trim")}>
            <option value="8.5x11">8.5 × 11 in (recommended)</option>
            <option value="8x10">8 × 10 in</option>
            <option value="8.5x8.5">8.5 × 8.5 in</option>
          </select>
        </Field>
        <p className="muted small">Defaults: paperback, black ink on white paper, no interior bleed, one blank back after every illustration. You can change these in Book setup.</p>
        <ErrorBox error={err} />
        <div className="row gap end">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Creating…" : "Create book"}</button>
        </div>
      </form>
    </Modal>
  );
}
