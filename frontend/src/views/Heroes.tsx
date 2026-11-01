import React, { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Field, Loading, Modal, useAsync, useToast } from "../ui";

/** Live check of a piece of text against the protected-name list. */
export function useIpCheck(text: string) {
  const [hits, setHits] = useState<any[]>([]);
  useEffect(() => {
    if (!text.trim()) { setHits([]); return; }
    const t = setTimeout(() => api.post("/api/ip-check", { text }).then((r) => setHits(r.hits)).catch(() => setHits([])), 300);
    return () => clearTimeout(t);
  }, [text]);
  return hits;
}

export function IpWarning({ text }: { text: string }) {
  const hits = useIpCheck(text);
  if (!hits.length) return null;
  return (
    <span className="warn-text small block" role="alert">
      ⚠ “{hits[0].matched}” belongs to {hits[0].owner}. Use an original name instead.
    </span>
  );
}

/** "3–5", "4–7" → a kids' style (youngest age ≤ 5 and oldest ≤ 7). */
export function isKidsPreset(p: any): boolean {
  const n = String(p.ages || "").match(/\d+/g)?.map(Number) || [];
  return n.length >= 2 && n[0] <= 5 && n[1] <= 7;
}

export function StylePresets({ pid, current, style, onApplied, kidsFirst = true }:
  { pid: string; current?: string; style?: any; onApplied: (sg: any) => void; kidsFirst?: boolean }) {
  const presets = useAsync(() => api.get("/api/style-presets"), []);
  const toast = useToast();
  const [onlyKids, setOnlyKids] = useState(kidsFirst);
  const [ask, setAsk] = useState<[string, any] | null>(null);
  if (presets.loading) return <Loading what="Loading style presets" />;
  if (!presets.data) return null;
  const hasMaster = !!(style?.master_style || "").trim();
  async function apply(key: string, p: any, master?: string) {
    try {
      const sg = await api.post(`/api/projects/${pid}/style/preset`, { key, master });
      setAsk(null);
      onApplied(sg);
      toast("ok", master === "replace" ? `“${p.label}” style text is now your master style. Your old text can be restored under Master style.`
        : master === "combine" ? `“${p.label}” style text added in front of your own master style.`
        : `Style preset “${p.label}” applied.`);
    } catch (e: any) { toast("err", e.message); }
  }
  const entries = Object.entries(presets.data.presets).filter(([, p]: any) => !onlyKids || isKidsPreset(p));
  return (
    <section className="card">
      <div className="row between wrap">
        <h2>Drawing style</h2>
        <div className="row gap" role="group" aria-label="Which styles to show">
          <button className={`btn btn-tiny ${onlyKids ? "btn-primary" : ""}`} aria-pressed={onlyKids} onClick={() => setOnlyKids(true)}>For ages 3–7</button>
          <button className={`btn btn-tiny ${!onlyKids ? "btn-primary" : ""}`} aria-pressed={!onlyKids} onClick={() => setOnlyKids(false)}>All styles</button>
        </div>
      </div>
      <p className="muted small">{presets.data.note} {hasMaster
        ? "This book has its own master style, which decides how pictures look – when you pick a style you can replace it, combine the two, or keep yours."
        : "The style you pick is used for every new picture and for planning scenes."}</p>
      <div className="preset-grid">
        {entries.map(([key, p]: any) => (
          <div key={key} className={`card preset ${current === key ? "preset-on" : ""}`}>
            <div className="row between"><strong>{p.label}</strong>{current === key ? <Badge kind="ok">in use</Badge> : p.ages && <Badge kind="info">ages {p.ages}</Badge>}</div>
            <p className="small">{p.description}</p>
            {p.best_for && <p className="small muted"><strong>Good for:</strong> {p.best_for}</p>}
            {p.master_style && <details className="small"><summary>Style text sent to the AI</summary><p className="muted">{p.master_style}</p></details>}
            <button className="btn btn-small" onClick={() => (hasMaster && p.master_style ? setAsk([key, p]) : apply(key, p))}>
              {current === key ? "Apply again" : "Use this style"}</button>
          </div>
        ))}
      </div>
      {ask && (
        <Modal title={`Use “${ask[1].label}”`} onClose={() => setAsk(null)}>
          <p>This book has its own <strong>master style</strong>, and the master style decides how pictures look. What should happen to it?</p>
          <blockquote className="small muted quote">{(style.master_style || "").slice(0, 400)}{(style.master_style || "").length > 400 ? "…" : ""}</blockquote>
          <div className="choice-list">
            <button className="btn btn-primary" onClick={() => apply(ask[0], ask[1], "replace")}>Use the “{ask[1].label}” style text instead</button>
            <span className="small muted">Your text is saved and can be restored.</span>
            <button className="btn" onClick={() => apply(ask[0], ask[1], "combine")}>Combine: the style's text first, then mine</button>
            <span className="small muted">Good when your text adds book details, such as a hidden object on every page or what the vehicles look like.</span>
            <button className="btn btn-ghost" onClick={() => apply(ask[0], ask[1], "keep")}>Keep my master style</button>
            <span className="small muted">The style then only changes scene planning; your text still decides the look.</span>
          </div>
        </Modal>
      )}
    </section>
  );
}

const HERO_FIELDS: [string, string, string][] = [
  ["name", "Hero name", "e.g. Captain Thunderpaw"],
  ["role", "Role on the team", "leader, flier, inventor…"],
  ["powers", "Powers", "talks to animals"],
  ["costume", "Costume", "hooded cape with a scalloped edge"],
  ["emblem", "Emblem", "a smiling sun"],
  ["appearance", "Appearance", "freckles, curly hair, big boots"],
  ["proportions", "Proportions", "head about 1/4 of body height"],
];

export function HeroTeam({ pid, style, setStyle, save }: any) {
  const toast = useToast();
  const team = style.team || {};
  const chars: any[] = style.characters || [];
  const setTeam = (k: string, v: string) => setStyle({ ...style, team: { ...team, [k]: v } });
  const setChar = (i: number, k: string, v: string) => { const cs = [...chars]; cs[i] = { ...cs[i], [k]: v }; setStyle({ ...style, characters: cs }); };
  async function suggest(kind: "hero" | "team") {
    const r = await api.post(`/api/projects/${pid}/heroes/suggest`, { kind, seed: Math.floor(Math.random() * 1e9), taken: chars.map((c) => c.name).filter(Boolean) });
    if (kind === "team") setStyle({ ...style, team: r });
    else setStyle({ ...style, characters: [...chars, r] });
    toast("info", "Suggestion added – edit it to make it yours, then save.");
  }
  return (
    <section className="card">
      <div className="row between">
        <h2>Original characters & hero team</h2>
        <button className="btn btn-primary" onClick={save}>Save characters & team</button>
      </div>
      <p className="muted small">
        Invent your own heroes instead of using existing ones. Names are checked against a list of well-known characters and brands as you type.
        It's only a list, not a legal search: also search any name on Amazon and the web before publishing.
      </p>
      <h3>Team</h3>
      <div className="grid2">
        {([["name", "Team name"], ["motto", "Motto"], ["headquarters", "Headquarters"], ["emblem", "Team emblem"]] as const).map(([k, l]) => (
          <Field key={k} label={l}>
            <input value={team[k] || ""} onChange={(e) => setTeam(k, e.target.value)} />
            <IpWarning text={team[k] || ""} />
          </Field>
        ))}
      </div>
      <button className="btn btn-small" onClick={() => suggest("team")}>Suggest an original team</button>
      <h3>Heroes & characters <Badge>{chars.length}</Badge></h3>
      <div className="hero-grid">
        {chars.map((c, i) => (
          <div key={i} className="card hero">
            {HERO_FIELDS.map(([k, l, ph]) => (
              <Field key={k} label={l}>
                <input value={c[k] || ""} placeholder={ph} onChange={(e) => setChar(i, k, e.target.value)} />
                {["name", "costume", "emblem"].includes(k) && <IpWarning text={c[k] || ""} />}
              </Field>
            ))}
            <button className="btn btn-small btn-ghost" onClick={() => setStyle({ ...style, characters: chars.filter((_, k) => k !== i) })}>Remove</button>
          </div>
        ))}
      </div>
      <div className="row gap">
        <button className="btn btn-small" onClick={() => suggest("hero")}>Suggest an original hero</button>
        <button className="btn btn-small" onClick={() => setStyle({ ...style, characters: [...chars, { name: "", role: "", powers: "", costume: "", emblem: "", appearance: "", proportions: "", reference_asset_ids: [] }] })}>+ Blank character</button>
      </div>
      <p className="muted small">Saved characters become scene subjects when you draft a plan, and are described in AI prompts if you use a provider.</p>
    </section>
  );
}

/** Master style: appended word-for-word to the END of every page prompt; replaces the app's own style lines. */
export function MasterStyle({ pid, style, onSaved }: { pid: string; style: any; onSaved: (sg: any) => void }) {
  const toast = useToast();
  const [text, setText] = useState<string>(style.master_style || "");
  const [mode, setMode] = useState<string>(style.cleanup_mode || "bold");
  useEffect(() => { setText(style.master_style || ""); setMode(style.cleanup_mode || "bold"); }, [style.master_style, style.cleanup_mode]);
  const looksFine = /stippl|hatch|fine|micron|intricate|0\.\d+ ?mm/i.test(text);
  const dirty = text !== (style.master_style || "") || mode !== (style.cleanup_mode || "bold");
  return (
    <div className="master-style">
      <Field label="Master style (added word-for-word to the end of every page prompt)" hint={`${text.length} / 3000 characters · when filled in, it replaces the app's built-in kids' style rules`}>
        <textarea rows={4} maxLength={3000} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Black-and-white adult coloring book page, pure white background, no grayscale shading, intricate pen-and-ink line art…" />
        <IpWarning text={text} />
      </Field>
      <Field label="Line-art cleanup after generation" help="Bold: removes small specks and pinholes – best for kids' books. Fine detail: keeps stippling dots, hatching and tiny shapes – for intricate adult styles.">
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="bold">Bold (kids' books – removes specks and tiny gaps)</option>
          <option value="fine">Fine detail (adult – keeps stippling and small shapes)</option>
        </select>
      </Field>
      {looksFine && mode === "bold" && <p className="warn-text small">Your master style asks for fine detail or stippling – choose “Fine detail” cleanup, or the dots will be removed as specks.</p>}
      {looksFine && <p className="small muted">Very thin lines (around 0.1 mm) can print faint or broken on KDP's paper. Order a printed proof before publishing.</p>}
      <button className="btn btn-small btn-primary" disabled={!dirty} onClick={async () => {
        try { const sg = await api.put(`/api/projects/${pid}/style`, { master_style: text, cleanup_mode: mode }); onSaved(sg); toast("ok", "Master style saved."); }
        catch (e: any) { toast("err", e.message); }
      }}>{dirty ? "Save master style" : "Saved"}</button>
      {style.previous_master_style && !dirty && (
        <details className="small"><summary>Your previous master style</summary>
          <p className="muted">{style.previous_master_style}</p>
          <button className="btn btn-tiny" onClick={async () => {
            const sg = await api.put(`/api/projects/${pid}/style`, { master_style: style.previous_master_style, previous_master_style: style.master_style || "" });
            onSaved(sg); toast("ok", "Previous master style restored.");
          }}>Restore it</button>
        </details>
      )}
    </div>
  );
}
