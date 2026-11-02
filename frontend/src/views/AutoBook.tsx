import React, { useContext, useEffect, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx } from "../App";
import { Badge, ErrorBox, Field, Loading, useAsync, useToast } from "../ui";
import { JobList, useJobs } from "./Export";
import { IpWarning, MasterStyle, StylePresets } from "./Heroes";
import { BriefPanel } from "./Brief";
import { ApproveAll } from "./ApproveAll";

export default function AutoBook() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const toast = useToast();
  const ai = useAsync(() => api.get("/api/ai/status"), []);
  const presets = useAsync(() => api.get("/api/style-presets"), []);
  const status = useAsync(() => api.get(`/api/projects/${pid}/autobook/status`), [pid]);
  const { jobs, active } = useJobs(pid);
  const [desc, setDesc] = useState(proj.spec.theme || "");
  const words = desc.trim() ? desc.trim().split(/\s+/).length : 0;
  const [count, setCount] = useState<number>(proj.spec.illustration_count || 20);
  const [preset, setPreset] = useState<string>(proj.style_guide.preset || "classic_cartoon");
  const [quality, setQuality] = useState("high");
  const [size, setSize] = useState<string>("");
  const [matchSample, setMatchSample] = useState(true);
  const [model, setModel] = useState<string>("");
  const [conn, setConn] = useState<any>(null);
  const [cfg, setCfg] = useState<any>({ key: "", per_image_estimate: "", spending_limit: "" });
  const [est, setEst] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!ai.data) return;
    setCfg((c: any) => ({ ...c, per_image_estimate: ai.data.settings.per_image_estimate ?? "", spending_limit: ai.data.settings.spending_limit ?? "" }));
    setModel(ai.data.status.model);
    const sizes = ai.data.capabilities.sizes || [];
    setSize((cur) => (sizes.includes(cur) ? cur : sizes[0] || ""));
  }, [ai.data]);
  useEffect(() => { if (!active) { status.reload(); refresh(); } }, [active]);

  const configured = ai.data?.status?.configured;
  const st = status.data;
  const genJobs = (jobs.data || []).filter((j: any) => j.type === "generate_images");
  const settings = { size, quality, auto_cleanup: true, match_sample: matchSample };

  async function run<T>(label: string, fn: () => Promise<T>) {
    setBusy(label); setErr(null);
    try { return await fn(); } catch (e) { setErr(e); } finally { setBusy(null); }
  }
  async function saveAi() {
    await run("Saving", async () => {
      if (cfg.key) await api.put("/api/ai/key", { api_key: cfg.key });
      await api.put("/api/ai/settings", { per_image_estimate: cfg.per_image_estimate, spending_limit: cfg.spending_limit, model });
      setCfg({ ...cfg, key: "" });
      await ai.reload();
      setConn(await api.post("/api/ai/test"));
      toast("ok", "AI settings saved on this computer.");
    });
  }
  async function plan() {
    await run("Planning pages", async () => {
      await api.post(`/api/projects/${pid}/autobook/plan`, { description: desc, count, preset });
      await refresh(); await status.reload();
      toast("ok", `Planned ${count} pages. Review the scene list in Plan & style if you like.`);
    });
  }
  async function generate(mode: "sample" | "rest" | "everything", confirm: boolean) {
    const r = await run(confirm ? "Starting" : "Checking cost", () => api.post(`/api/projects/${pid}/autobook/generate`, { mode, settings, confirm }));
    if (!r) return;
    if (!confirm) setEst({ ...r, mode });
    else { setEst(null); jobs.reload(); toast("info", mode === "sample" ? "Making your sample page…" : "Generating your pages – you can leave this screen open."); }
  }
  const sample = st?.pages.find((p: any) => p.version_id);
  const sampleAsset = useAsync(async () => (sample ? api.get(`/api/versions/${sample.version_id}`) : null), [sample?.version_id]);

  return (
    <div className="page">
      <h1>Create with AI</h1>
      <p className="lede">Describe your book once. The app plans every page, makes one sample for you to check, then creates the rest – cleaned to pure black-and-white line art and placed on the pages, with a colored cover image.</p>

      <BriefPanel pid={pid} onApplied={() => { refresh(); status.reload(); }} />

      <section className="card">
        <h2>1. AI image service {configured ? <Badge kind="ok">connected</Badge> : <Badge kind="warn">not set up</Badge>}</h2>
        {ai.loading && <Loading />}
        {ai.data && (
          <>
            <p className="small muted">Uses OpenAI's image API with your own API key (create one at platform.openai.com). Every image is billed to your OpenAI account – check their current prices. The key stays on this computer.</p>
            {!ai.data.status.live && <p className="note">⚠ {ai.data.status.note}</p>}
            <div className="grid3">
              <Field label={configured ? "API key (saved – paste to replace)" : "OpenAI API key"}><input type="password" autoComplete="off" value={cfg.key} onChange={(e) => setCfg({ ...cfg, key: e.target.value })} placeholder={configured ? "••••••••" : "sk-…"} /></Field>
              <Field label="Your cost per image (from OpenAI's price page)" hint="Needed for batches so the app can stop at your limit."><input type="number" step="0.001" min={0} value={cfg.per_image_estimate} onChange={(e) => setCfg({ ...cfg, per_image_estimate: e.target.value })} /></Field>
              <Field label="Spending limit"><input type="number" step="0.5" min={0} value={cfg.spending_limit} onChange={(e) => setCfg({ ...cfg, spending_limit: e.target.value })} /></Field>
            </div>
            <div className="grid2">
              <Field label="Model">
                <select value={model} onChange={(e) => setModel(e.target.value)}>
                  {(ai.data.capabilities.models || []).map((m: any) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </Field>
            </div>
            <div className="row gap wrap">
              <button className="btn btn-primary" onClick={saveAi} disabled={!!busy}>Save & test connection</button>
              {configured && <button className="btn" disabled={!!busy} onClick={async () => setConn(await api.post("/api/ai/test"))}>Test connection (free)</button>}
            </div>
            {conn && <p className={conn.ok ? "ok-text" : "warn-text"} role="status">{conn.ok ? "✓ " : "⚠ "}{conn.message}</p>}
          </>
        )}
      </section>

      <section className="card form-grid">
        <h2>2. Describe your book</h2>
        <Field label="Description" hint="Theme, audience and the kind of characters. Original characters only.">
          <textarea rows={14} maxLength={90000} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Cute original sea animals having beach adventures for kids 4–7: a shy octopus, a brave crab and a silly seagull… Describe the characters' looks and personalities, places, activities, mood and anything to avoid – up to 10,000 words. Tip: give each character or place its own paragraph." />
          <span className={`small ${words > 9500 ? "warn-text" : "muted"}`}>{words.toLocaleString()} / 10,000 words</span>
          {desc.length > 29000 && <span className="small muted block">Your description is longer than one OpenAI request can hold (about 5,000 words). Each picture gets your opening overview plus the paragraphs that mention that page's characters and setting, so put the most important points first and give each character its own paragraph.</span>}
          <IpWarning text={desc} />
        </Field>
        <div className="grid2">
          <Field label="Number of illustrations"><input type="number" min={1} max={200} value={count} onChange={(e) => setCount(+e.target.value)} /></Field>
          <Field label="Style">
            <select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {presets.data && Object.entries(presets.data.presets).map(([k, p]: any) => <option key={k} value={k}>{p.label}</option>)}
            </select>
          </Field>
        </div>
        <p className="small muted">This makes a {proj.spec.intro_pages + count * (proj.spec.blank_backs ? 2 : 1)}-page book ({proj.spec.intro_pages} intro pages{proj.spec.blank_backs ? " + a blank back after each picture" : ""}).
          {proj.spec.intro_pages + count * (proj.spec.blank_backs ? 2 : 1) < 24 && <span className="warn-text"> KDP needs at least 24 pages – choose at least {Math.ceil((24 - proj.spec.intro_pages) / (proj.spec.blank_backs ? 2 : 1))} illustrations.</span>}</p>
        <MasterStyle pid={pid} style={proj.style_guide} onSaved={() => refresh()} />
        <StylePresets pid={pid} current={proj.style_guide.preset} style={proj.style_guide}
          kidsFirst={!((proj.spec.audience || "").toLowerCase().startsWith("adult"))}
          onApplied={(sg: any) => { setPreset(sg.preset); refresh(); }} />
        <button className="btn btn-primary" disabled={!!busy || desc.trim().length < 10 || words > 10000} onClick={plan}>Plan my pages</button>
        {proj.scenes.length > 0 && <p className="small muted">{proj.scenes.length} scenes planned · <a href={`#/p/${pid}/plan`}>review or edit them</a> (characters from your hero team are used automatically).</p>}
        <p className="small"><a href={`#/p/${pid}/descriptions`}><strong>✎ Write a description for each page →</strong></a> <span className="muted">Pages with your own description use it instead of the automatic plan; re-planning keeps them.</span></p>
      </section>

      {st?.unimported > 0 && (
        <div className="banner banner-info">
          {st.unimported} paid image(s) were received from OpenAI but not added to the book.
          <button className="btn btn-small" onClick={async () => { const r = await run("Recovering", () => api.post(`/api/projects/${pid}/generations/recover`)); if (r) { toast("ok", `Added ${r.recovered_asset_ids.length} image(s).`); status.reload(); refresh(); } }}>Add them now</button>
        </div>
      )}

      <section className="card">
        <h2>3. Make a sample page</h2>
        <p className="small muted">One image first, so you can check the style before paying for the whole book.</p>
        <div className="grid3">
          <Field label="Image size" help="Bigger images print sharper. 2400×3200 is about 320 DPI on a full page – real print resolution.">
            <select value={size} onChange={(e) => setSize(e.target.value)}>
              {(ai.data?.capabilities?.size_presets || []).map((p: any) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </Field>
          <Field label="Quality"><select value={quality} onChange={(e) => setQuality(e.target.value)}>{(ai.data?.capabilities?.quality || ["high"]).map((q: string) => <option key={q}>{q}</option>)}</select></Field>
          <label className="check-inline"><input type="checkbox" checked={matchSample} onChange={(e) => setMatchSample(e.target.checked)} /> Match the approved sample's style (more consistent pages; each request also sends the sample image, which costs a little more)</label>
        </div>
        <div className="row gap wrap">
          <button className="btn btn-primary" disabled={!configured || !!busy || active || !st?.empty_scene_ids?.length} onClick={() => generate("sample", false)}>Make sample page</button>
        </div>
        {sample && sampleAsset.data && (
          <div className="sample">
            <img src={img(sample.version_id, 500)} alt="Sample page" />
            <div>
              <p><strong>{sample.label}</strong></p>
              {st.approved_sample ? <p className="ok-text">✓ Sample approved – you can create the rest.</p> : (
                <div className="row gap wrap">
                  <button className="btn btn-primary" onClick={async () => { await api.patch(`/api/assets/${sampleAsset.data.asset_id}`, { review_status: "approved" }); status.reload(); toast("ok", "Sample approved."); }}>Looks good – approve</button>
                  <button className="btn" disabled={active} onClick={async () => { const r = await run("Starting", () => api.post(`/api/pages/${sample.page_id}/regenerate`, { settings, confirm: true })); if (r) jobs.reload(); }}>Try again</button>
                </div>
              )}
              <p className="small muted">Tip: if the style is off, adjust the description or style and plan again.</p>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2>4. Create the rest</h2>
        <div className="row gap wrap">
          <button className="btn btn-primary" disabled={!configured || !st?.approved_sample || !!busy || active} onClick={() => generate("everything", false)}>
            Create everything (pages, intro art & covers)
          </button>
          <button className="btn" disabled={!configured || !st?.approved_sample || !!busy || active || !st?.empty_scene_ids?.length} onClick={() => generate("rest", false)}>
            Only the remaining {st?.empty_scene_ids?.length ?? 0} pages
          </button>
        </div>
        {est && (
          <div className="estimate">
            <dl className="facts">
              <dt>Images</dt><dd>{est.count}{est.breakdown ? ` (${est.breakdown.pages} pages, ${est.breakdown.intro} intro, ${est.breakdown.front_cover ? "front cover" : "no front cover"}, ${est.breakdown.back_cover ? "back cover" : "no back cover"})` : ""}</dd>
              <dt>Estimated cost</dt><dd>{est.estimated_cost}</dd>
              <dt>Your limit</dt><dd>{est.budget.spending_limit ?? "not set"} (estimated so far {est.budget.estimated_spent})</dd>
            </dl>
            {est.problems.map((p: string) => <p key={p} className="warn-text">{p}</p>)}
            <p className="small muted">{est.warning}</p>
            <button className="btn btn-primary" disabled={!est.allowed} onClick={() => generate(est.mode, true)}>Generate {est.count} image{est.count > 1 ? "s" : ""}</button>
            <button className="btn btn-ghost" onClick={() => setEst(null)}>Cancel</button>
          </div>
        )}
        {busy && <Loading what={busy} />}
        <ErrorBox error={err} />
        <JobList jobs={genJobs} onChange={jobs.reload} />
      </section>

      <section className="card">
        <h2>Cover art (optional)</h2>
        <p className="small muted">A full-color AI illustration for the front cover (no text – the title is added by the cover designer). Without it, the app makes a colored version of your first page.</p>
        <button className="btn" disabled={!configured || !!busy || active} onClick={async () => {
          const e = await run("Checking cost", () => api.post(`/api/projects/${pid}/autobook/cover`, { settings }));
          if (e && confirm(`Generate 1 cover image? Estimated cost: ${e.estimated_cost}.`)) {
            const r = await run("Starting", () => api.post(`/api/projects/${pid}/autobook/cover`, { settings, confirm: true }));
            if (r) { jobs.reload(); toast("info", "Making cover art…"); }
          }
        }}>Generate AI cover art</button>
        {proj.cover.data.front_art_version_id && <div className="sample"><img src={img(proj.cover.data.front_art_version_id, 400)} alt="Current cover art" /><p className="small"><a href={`#/p/${pid}/cover`}>Open the cover designer →</a></p></div>}
      </section>

      {st && st.pages.some((p: any) => p.version_id) && (
        <section className="card">
          <div className="row between wrap">
            <h2>5. Review your pages</h2>
            <ApproveAll pid={pid} author={proj.spec.author} small onDone={() => { refresh(); status.reload(); }} />
          </div>
          <p className="small muted">Approve the ones you like; regenerate the rest (approved pages are never replaced). Then check the <a href={`#/p/${pid}/cover`}>cover</a>, run <a href={`#/p/${pid}/preflight`}>preflight</a> and <a href={`#/p/${pid}/export`}>export</a>.</p>
          <div className="book-grid">
            {st.pages.map((p: any) => (
              <div key={p.page_id} className="pcard">
                <div className="pcard-thumb" onClick={() => (window.location.hash = `#/p/${pid}/editor/${p.page_id}`)}>
                  {p.version_id ? <img src={img(p.version_id, 220)} alt={p.label} loading="lazy" /> : <span className="muted small">waiting</span>}
                </div>
                <div className="pcard-label" title={p.label}>{p.label}</div>
                {(p.check || []).map((c: string) => <Badge key={c} kind="warn">{c}</Badge>)}
                {p.version_id && (
                  <div className="row gap wrap">
                    <button className={`btn btn-tiny ${p.approved ? "btn-ok" : ""}`} onClick={async () => { await api.post(`/api/pages/${p.page_id}/approve`, { approved: !p.approved }); status.reload(); }}>{p.approved ? "✓ Approved" : "Approve"}</button>
                    {!p.approved && <button className="btn btn-tiny" disabled={active} onClick={async () => { const r = await run("Starting", () => api.post(`/api/pages/${p.page_id}/regenerate`, { settings, confirm: true })); if (r) jobs.reload(); }}>Regenerate</button>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
