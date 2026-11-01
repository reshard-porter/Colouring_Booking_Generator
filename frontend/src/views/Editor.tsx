import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx, go } from "../App";
import { Badge, ErrorBox, Field, Loading, Modal, useToast } from "../ui";

type El = any;
const PT = 72; // SVG user units are PDF points so fonts render at true size
const r4 = (v: number) => Math.round(v * 10000) / 10000;

function cropPx(v: any, crop: any) {
  const c = crop || {};
  const l = +c.l || 0, t = +c.t || 0, r = +c.r || 0, b = +c.b || 0;
  return { x0: v.width_px * l, y0: v.height_px * t, cw: v.width_px * (1 - l - r), ch: v.height_px * (1 - t - b) };
}
export function elRect(el: El, v?: any) {
  if (el.kind === "image" && v) {
    const { cw, ch } = cropPx(v, el.crop);
    return { x: +el.x, y: +el.y, w: +el.w, h: (+el.w * ch) / cw };
  }
  return { x: +el.x, y: +el.y, w: +el.w, h: +(el.h || 0) };
}

export default function Editor({ pageId }: { pageId: string }) {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const toast = useToast();
  const [page, setPage] = useState<any>(null);
  const [geo, setGeo] = useState<any>(null);
  const [els, setEls] = useState<El[]>([]);
  const [versions, setVersions] = useState<Record<string, any>>({});
  const [sel, setSel] = useState<string | null>(null);
  const [past, setPast] = useState<El[][]>([]);
  const [future, setFuture] = useState<El[][]>([]);
  const [save, setSave] = useState<"saved" | "saving" | "unsaved" | "error">("saved");
  const [saveErr, setSaveErr] = useState<string>("");
  const [ov, setOv] = useState({ trim: true, safe: true, gutter: true });
  const [mode, setMode] = useState<"select" | "erase">("select");
  const [eraseShapes, setEraseShapes] = useState<any[]>([]);
  const [compare, setCompare] = useState<any>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [hist, setHist] = useState<any[] | null>(null);
  const [assetInfo, setAssetInfo] = useState<any>(null);
  const [loadErr, setLoadErr] = useState<any>(null);
  const [tool, setTool] = useState({ brightness: 1, contrast: 1.2, level: 160, min_area: 40 });
  const [busy, setBusy] = useState<string | null>(null);
  const dirty = useRef(false);
  const elsRef = useRef<El[]>([]);
  elsRef.current = els;

  const load = useCallback(async () => {
    try {
      const r = await api.get(`/api/pages/${pageId}`);
      setPage(r.page);
      setGeo(r.geometry);
      setEls(r.page.elements);
      setLoadErr(null);
    } catch (e) {
      setLoadErr(e);
    }
  }, [pageId]);
  useEffect(() => { load(); }, [load]);

  // version metadata for image elements
  useEffect(() => {
    const need = els.filter((e) => e.kind === "image" && !versions[e.asset_version_id]).map((e) => e.asset_version_id);
    if (!need.length) return;
    Promise.all(need.map((v) => api.get(`/api/versions/${v}`))).then((vs) =>
      setVersions((cur) => ({ ...cur, ...Object.fromEntries(vs.map((v: any) => [v.id, v])) }))
    );
  }, [els]);

  // ---- edits, undo/redo, autosave ----
  const commit = useCallback((next: El[]) => {
    setPast((p) => [...p.slice(-80), elsRef.current]);
    setFuture([]);
    setEls(next);
    dirty.current = true;
    setSave("unsaved");
  }, []);
  const update = (id: string, patch: any, record = true) => {
    const next = elsRef.current.map((e) => (e.id === id ? { ...e, ...patch } : e));
    if (record) commit(next);
    else setEls(next);
  };
  const undo = () => {
    if (!past.length) return;
    setFuture((f) => [els, ...f]);
    setEls(past[past.length - 1]);
    setPast(past.slice(0, -1));
    dirty.current = true;
    setSave("unsaved");
  };
  const redo = () => {
    if (!future.length) return;
    setPast((p) => [...p, els]);
    setEls(future[0]);
    setFuture(future.slice(1));
    dirty.current = true;
    setSave("unsaved");
  };
  const flush = useCallback(async () => {
    if (!dirty.current) return true;
    dirty.current = false;
    setSave("saving");
    try {
      const p = await api.put(`/api/pages/${pageId}/elements`, { elements: elsRef.current });
      setPage(p);
      setSave(dirty.current ? "unsaved" : "saved");
      setSaveErr("");
      return true;
    } catch (e: any) {
      dirty.current = true;
      setSave("error");
      setSaveErr(e.message);
      return false;
    }
  }, [pageId]);
  useEffect(() => {
    if (save !== "unsaved") return;
    const t = setTimeout(flush, 800);
    return () => clearTimeout(t);
  }, [els, save, flush]);
  useEffect(() => {
    const beforeUnload = (e: BeforeUnloadEvent) => { if (dirty.current) { e.preventDefault(); } };
    window.addEventListener("beforeunload", beforeUnload);
    return () => { window.removeEventListener("beforeunload", beforeUnload); flush().then(() => refresh()); };
  }, []);

  const selEl = els.find((e) => e.id === sel);
  const selV = selEl?.kind === "image" ? versions[selEl.asset_version_id] : null;

  // keyboard
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
      if (!selEl) return;
      const step = e.shiftKey ? 0.25 : 0.05;
      const mv: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
      if (mv[e.key]) { e.preventDefault(); update(selEl.id, { x: r4(+selEl.x + mv[e.key][0]), y: r4(+selEl.y + mv[e.key][1]) }); }
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); commit(els.filter((x) => x.id !== selEl.id)); setSel(null); }
      if (e.key === "Escape") { setSel(null); setMode("select"); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  // ---- pointer interactions ----
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<any>(null);
  const toIn = (e: React.PointerEvent | PointerEvent) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: p.x / PT - geo.trim_origin_x, y: p.y / PT - geo.trim_origin_y };
  };
  function down(e: React.PointerEvent, el: El, kind: "move" | "resize") {
    e.stopPropagation();
    setSel(el.id);
    const p = toIn(e);
    if (mode === "erase" && el.kind === "image" && kind === "move") {
      drag.current = { kind: "erase", start: p, el };
    } else {
      drag.current = { kind, start: p, orig: { ...el }, base: elsRef.current };
    }
    (e.target as Element).setPointerCapture(e.pointerId);
  }
  function moveP(e: React.PointerEvent) {
    const d = drag.current;
    if (!d) return;
    const p = toIn(e);
    const dx = p.x - d.start.x, dy = p.y - d.start.y;
    if (d.kind === "move") update(d.orig.id, { x: r4(+d.orig.x + dx), y: r4(+d.orig.y + dy) }, false);
    else if (d.kind === "resize") {
      const w = Math.max(0.2, +d.orig.w + dx);
      update(d.orig.id, d.orig.kind === "image" ? { w: r4(w) } : { w: r4(w), h: r4(Math.max(0, +d.orig.h + dy)) }, false);
    } else if (d.kind === "erase") d.cur = p;
    if (d.kind === "erase") setEraseShapes((s) => [...s.filter((x) => !x.live), { live: true, a: d.start, b: p }]);
  }
  function up() {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.kind === "erase") {
      const v = versions[d.el.asset_version_id];
      const r = elRect(d.el, v);
      const { x0, y0, cw, ch } = cropPx(v, d.el.crop);
      const a = d.start, b = d.cur || d.start;
      const nx = (px: number) => (x0 + ((Math.min(Math.max(px, r.x), r.x + r.w) - r.x) / r.w) * cw) / v.width_px;
      const ny = (py: number) => (y0 + ((Math.min(Math.max(py, r.y), r.y + r.h) - r.y) / r.h) * ch) / v.height_px;
      const sx = nx(Math.min(a.x, b.x)), sy = ny(Math.min(a.y, b.y));
      const shape = { shape: "rect", x: sx, y: sy, w: nx(Math.max(a.x, b.x)) - sx, h: ny(Math.max(a.y, b.y)) - sy, a, b };
      setEraseShapes((s) => [...s.filter((x) => !x.live), ...(shape.w > 0.002 && shape.h > 0.002 ? [shape] : [])]);
      return;
    }
    // record the drag as a single undo step
    setPast((p) => [...p.slice(-80), d.base]);
    setFuture([]);
    dirty.current = true;
    setSave("unsaved");
  }

  // ---- image operations (new immutable versions) ----
  async function derive(op: any, label: string) {
    if (!selEl || selEl.kind !== "image") return;
    setBusy(label);
    try {
      const before = selEl.asset_version_id;
      const nv = await api.post(`/api/versions/${before}/derive`, op);
      setVersions((v) => ({ ...v, [nv.id]: nv }));
      update(selEl.id, { asset_version_id: nv.id });
      setCompare({ before, after: nv.id, elId: selEl.id, label });
      toast("ok", `${label}: new version v${nv.version_no} created. The original is kept.`);
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(null);
    }
  }
  async function fit(target: "safe" | "trim") {
    if (!selEl || selEl.kind !== "image") return;
    const r = await api.post(`/api/pages/${pageId}/fit`, { element: selEl, target });
    update(selEl.id, { x: r.x, y: r.y, w: r.w });
  }
  function align(how: string) {
    if (!selEl || !geo) return;
    const r = elRect(selEl, selV);
    const s = geo.safe;
    const patch: any = {};
    if (how === "left") patch.x = s.x;
    if (how === "hcenter") patch.x = r4(s.x + (s.w - r.w) / 2);
    if (how === "right") patch.x = r4(s.x + s.w - r.w);
    if (how === "top") patch.y = s.y;
    if (how === "vcenter") patch.y = r4(s.y + (s.h - r.h) / 2);
    if (how === "bottom") patch.y = r4(s.y + s.h - r.h);
    update(selEl.id, patch);
  }
  async function showAsset() {
    if (!selV) return;
    setAssetInfo(await api.get(`/api/assets/${selV.asset_id}`));
  }

  if (loadErr) return <ErrorBox error={loadErr} retry={load} />;
  if (!page || !geo) return <Loading what="Loading page" />;

  const contentPages = proj.pages;
  const idx = contentPages.findIndex((p: any) => p.id === pageId);
  const num = proj.assembly.pages.find((x: any) => x.page_id === pageId)?.number;
  const W = geo.media_w * PT, H = geo.media_h * PT;
  const T = (v: number) => v * PT;
  const dpi = selEl?.kind === "image" && selV ? (() => {
    const { cw } = cropPx(selV, selEl.crop);
    const raw = cw / +selEl.w;
    return selV.upscaled ? (raw * selV.original_width_px) / selV.width_px : raw;
  })() : null;

  return (
    <div className="editor">
      <aside className="ed-strip" aria-label="Pages">
        {contentPages.map((p: any) => {
          const im = p.elements.find((x: any) => x.kind === "image");
          return (
            <button key={p.id} className={`strip-item ${p.id === pageId ? "active" : ""}`} onClick={async () => { await flush(); go(`/p/${pid}/editor/${p.id}`); }} aria-current={p.id === pageId}>
              {im ? <img src={img(im.asset_version_id, 120)} alt="" loading="lazy" /> : <span className="strip-ph">{p.kind === "intro" ? "Aa" : "—"}</span>}
              <span className="small">{p.label}</span>
            </button>
          );
        })}
      </aside>

      <section className="ed-center">
        <div className="ed-toolbar" role="toolbar" aria-label="Editor tools">
          <a className="btn btn-small" href={`#/p/${pid}/pages`}>← Pages</a>
          <button className="btn btn-small" disabled={idx <= 0} onClick={async () => { await flush(); go(`/p/${pid}/editor/${contentPages[idx - 1].id}`); }}>‹ Prev</button>
          <button className="btn btn-small" disabled={idx >= contentPages.length - 1} onClick={async () => { await flush(); go(`/p/${pid}/editor/${contentPages[idx + 1].id}`); }}>Next ›</button>
          <strong className="ed-title">p.{num} · {page.label}</strong>
          <button className="btn btn-small" onClick={undo} disabled={!past.length} title="Undo (Ctrl+Z)">↶ Undo</button>
          <button className="btn btn-small" onClick={redo} disabled={!future.length} title="Redo (Ctrl+Shift+Z)">↷ Redo</button>
          <span className={`save save-${save}`} role="status" aria-live="polite">
            {save === "saved" ? "✓ Saved" : save === "saving" ? "Saving…" : save === "unsaved" ? "Unsaved changes" : `⚠ Not saved: ${saveErr}`}
          </span>
          {save === "error" && <button className="btn btn-small" onClick={flush}>Retry save</button>}
          {page.kind === "illustration" && (
            <button className={`btn btn-small ${page.approved ? "btn-ok" : "btn-primary"}`} onClick={async () => { await flush(); const p = await api.post(`/api/pages/${pageId}/approve`, { approved: !page.approved }); setPage(p); toast("ok", p.approved ? "Page approved." : "Approval removed."); }}>
              {page.approved ? "✓ Approved" : "Approve page"}
            </button>
          )}
        </div>
        <div className="ed-toolbar secondary">
          <label className="check-inline"><input type="checkbox" checked={ov.trim} onChange={(e) => setOv({ ...ov, trim: e.target.checked })} /> Trim</label>
          <label className="check-inline"><input type="checkbox" checked={ov.safe} onChange={(e) => setOv({ ...ov, safe: e.target.checked })} /> Safe area</label>
          <label className="check-inline"><input type="checkbox" checked={ov.gutter} onChange={(e) => setOv({ ...ov, gutter: e.target.checked })} /> Binding side</label>
          <span className="muted small">Guides are screen-only and never printed.</span>
          <button className="btn btn-small" onClick={async () => { await flush(); setPreview(`/api/pages/${pageId}/preview.png?dpi=80&t=${Date.now()}`); }}>Exact print preview</button>
        </div>
        <div className="canvas-wrap" onPointerDown={() => mode === "select" && setSel(null)}>
          <svg ref={svgRef} className="canvas" viewBox={`0 0 ${W} ${H}`} onPointerMove={moveP} onPointerUp={up} role="img" aria-label={`Page ${num} canvas`}>
            <rect x={0} y={0} width={W} height={H} fill="#fff" />
            {geo.media_w !== geo.trim.w && <rect x={0} y={0} width={W} height={H} fill="none" stroke="#e66" strokeDasharray="6 4" strokeWidth={1} />}
            <g transform={`translate(${T(geo.trim_origin_x)} ${T(geo.trim_origin_y)})`}>
              {ov.gutter && (
                <rect x={geo.inside_edge === "left" ? 0 : T(geo.trim.w - geo.inside_margin)} y={0} width={T(geo.inside_margin)} height={T(geo.trim.h)} fill="rgba(120,140,220,.12)" />
              )}
              {els.map((el) => {
                const v = el.kind === "image" ? versions[el.asset_version_id] : null;
                if (el.kind === "image" && !v) return null;
                const r = elRect(el, v);
                const cx = T(r.x + r.w / 2), cy = T(r.y + r.h / 2);
                const isSel = el.id === sel;
                return (
                  <g key={el.id} transform={`rotate(${+el.rotation || 0} ${cx} ${cy})`}>
                    <g onPointerDown={(e) => down(e, el, "move")} style={{ cursor: mode === "erase" && el.kind === "image" ? "crosshair" : "move" }}>
                      {el.kind === "image" && (() => {
                        const { x0, y0, cw, ch } = cropPx(v, el.crop);
                        return (
                          <svg x={T(r.x)} y={T(r.y)} width={T(r.w)} height={T(r.h)} viewBox={`${x0} ${y0} ${cw} ${ch}`} preserveAspectRatio="none">
                            <image href={img(el.asset_version_id, 1400)} width={v.width_px} height={v.height_px} preserveAspectRatio="none" />
                          </svg>
                        );
                      })()}
                      {el.kind === "text" && (
                        <foreignObject x={T(r.x)} y={T(r.y)} width={T(r.w)} height={Math.max(T(r.h), 1)}>
                          <div className="svg-text" style={{ fontSize: `${el.size_pt}px`, fontWeight: el.bold ? 700 : 400, textAlign: el.align || "left" }}>{el.text}</div>
                        </foreignObject>
                      )}
                      {el.kind === "shape" && el.shape === "line" && <line x1={T(r.x)} y1={T(r.y)} x2={T(r.x + r.w)} y2={T(r.y + r.h)} stroke="#000" strokeWidth={el.stroke_pt || 2.5} />}
                      {el.kind === "shape" && el.shape !== "line" && <rect x={T(r.x)} y={T(r.y)} width={T(r.w)} height={T(r.h)} rx={Math.min(T(r.w), T(r.h)) * 0.08} fill="none" stroke="#000" strokeWidth={el.stroke_pt || 2.5} />}
                      <rect className="hit" data-kind={el.kind} x={T(r.x)} y={T(r.y) - (el.kind === "shape" ? 4 : 0)} width={T(r.w)} height={Math.max(T(r.h), 8)} fill="transparent" stroke={isSel ? "#2a7de1" : "transparent"} strokeWidth={1.5} strokeDasharray={isSel ? "" : "3 3"} />
                    </g>
                    {isSel && mode === "select" && (
                      <rect x={T(r.x + r.w) - 7} y={T(r.y + r.h) - 7} width={14} height={14} fill="#2a7de1" style={{ cursor: "nwse-resize" }} onPointerDown={(e) => down(e, el, "resize")} aria-label="Resize handle" />
                    )}
                  </g>
                );
              })}
              {eraseShapes.map((s, i) => (
                <rect key={i} x={T(Math.min(s.a.x, s.b.x))} y={T(Math.min(s.a.y, s.b.y))} width={T(Math.abs(s.b.x - s.a.x))} height={T(Math.abs(s.b.y - s.a.y))} fill="rgba(255,80,80,.25)" stroke="#e33" strokeDasharray="4 3" pointerEvents="none" />
              ))}
              {ov.trim && <rect x={0} y={0} width={T(geo.trim.w)} height={T(geo.trim.h)} fill="none" stroke="#999" strokeWidth={1} pointerEvents="none" />}
              {ov.safe && <rect x={T(geo.safe.x)} y={T(geo.safe.y)} width={T(geo.safe.w)} height={T(geo.safe.h)} fill="none" stroke="#2bb673" strokeDasharray="8 5" strokeWidth={1.2} pointerEvents="none" />}
            </g>
          </svg>
        </div>
        <p className="muted small center">
          Canvas is {geo.trim.w} × {geo.trim.h} in trim{geo.media_w !== geo.trim.w ? ` with bleed (${geo.media_w} × ${geo.media_h} in)` : ""}. Green dashed = safe area ({geo.inside_margin} in binding side, {geo.outside_margin} in other edges). Shaded = binding (gutter) side. Arrow keys nudge, Shift+arrows nudge more, Delete removes.
        </p>
      </section>

      <aside className="ed-props" aria-label="Properties">
        <div className="row gap wrap">
          <button className="btn btn-small" onClick={() => setPicker(true)}>{els.some((e) => e.kind === "image") ? "Replace artwork" : "+ Add artwork"}</button>
          <button className="btn btn-small" onClick={() => { const id = `el_${Math.random().toString(16).slice(2, 10)}`; commit([...els, { id, kind: "text", x: geo.safe.x, y: geo.safe.y, w: geo.safe.w, h: 0.8, text: "New text", size_pt: 24, bold: true, align: "center" }]); setSel(id); }}>+ Text</button>
          <button className="btn btn-small" onClick={async () => setHist(await api.get(`/api/pages/${pageId}/history`))}>Page history</button>
        </div>
        {!selEl && <p className="muted">Select something on the page to edit it.</p>}
        {selEl && (
          <div className="props">
            <h3>{selEl.kind === "image" ? "Artwork" : selEl.kind === "text" ? "Text" : "Shape"}</h3>
            <div className="grid2">
              <Field label="X (in)"><input type="number" step="0.05" value={selEl.x} onChange={(e) => update(selEl.id, { x: +e.target.value })} /></Field>
              <Field label="Y (in)"><input type="number" step="0.05" value={selEl.y} onChange={(e) => update(selEl.id, { y: +e.target.value })} /></Field>
              <Field label="Width (in)"><input type="number" step="0.05" min={0.1} value={selEl.w} onChange={(e) => +e.target.value > 0 && update(selEl.id, { w: +e.target.value })} /></Field>
              {selEl.kind !== "image" ? (
                <Field label="Height (in)"><input type="number" step="0.05" min={0} value={selEl.h} onChange={(e) => update(selEl.id, { h: +e.target.value })} /></Field>
              ) : (
                <Field label="Height (in)" hint="Locked to the artwork's proportions"><input readOnly value={elRect(selEl, selV).h.toFixed(3)} /></Field>
              )}
              {selEl.kind === "image" && <Field label="Rotation (°)"><input type="number" step="1" value={selEl.rotation || 0} onChange={(e) => update(selEl.id, { rotation: +e.target.value })} /></Field>}
            </div>
            {selEl.kind === "image" && selV && (
              <>
                <div className="row gap wrap">
                  <button className="btn btn-small" onClick={() => fit("safe")}>Fit to safe area</button>
                  <button className="btn btn-small" onClick={() => fit("trim")}>Fit to page</button>
                  <button className="btn btn-small" onClick={() => update(selEl.id, { rotation: ((+selEl.rotation || 0) + 90) % 360 })}>Rotate 90°</button>
                </div>
                <p className={dpi! < 300 ? "warn-text" : "ok-text"}>
                  Effective resolution: <strong>{dpi!.toFixed(0)} DPI</strong> at this size {dpi! < 300 ? "(below the 300 DPI target)" : "✓"}
                  {selV.upscaled && <span className="block small">This version was enlarged from {selV.original_width_px}px; DPI shown uses the original detail.</span>}
                </p>
                <h4>Crop (non-destructive)</h4>
                <div className="grid2">
                  {(["l", "r", "t", "b"] as const).map((k) => (
                    <Field key={k} label={{ l: "Left %", r: "Right %", t: "Top %", b: "Bottom %" }[k]}>
                      <input type="range" min={0} max={45} step={0.5} value={(+(selEl.crop?.[k] || 0) * 100)} onChange={(e) => update(selEl.id, { crop: { l: 0, t: 0, r: 0, b: 0, ...selEl.crop, [k]: +e.target.value / 100 } })} aria-label={`Crop ${k}`} />
                    </Field>
                  ))}
                </div>
                <h4>Image tools <span className="muted small">(each creates a new version; original kept)</span></h4>
                <div className="grid2">
                  <Field label={`Brightness ${tool.brightness}`}><input type="range" min={0.5} max={1.8} step={0.05} value={tool.brightness} onChange={(e) => setTool({ ...tool, brightness: +e.target.value })} /></Field>
                  <Field label={`Contrast ${tool.contrast}`}><input type="range" min={0.5} max={3} step={0.05} value={tool.contrast} onChange={(e) => setTool({ ...tool, contrast: +e.target.value })} /></Field>
                </div>
                <button className="btn btn-small" disabled={!!busy} onClick={() => derive({ type: "adjust", brightness: tool.brightness, contrast: tool.contrast }, "Brightness/contrast")}>Apply brightness/contrast</button>
                <Field label={`Threshold level ${tool.level}`} help="Turns every pixel pure black or pure white. Removes gray shading and scan noise; can thin faint lines."><input type="range" min={60} max={230} value={tool.level} onChange={(e) => setTool({ ...tool, level: +e.target.value })} /></Field>
                <button className="btn btn-small" disabled={!!busy} onClick={() => derive({ type: "threshold", level: tool.level }, "Threshold")}>Apply threshold</button>
                <Field label={`Cleanup: remove specks under ${tool.min_area}px`}><input type="range" min={5} max={400} value={tool.min_area} onChange={(e) => setTool({ ...tool, min_area: +e.target.value })} /></Field>
                <button className="btn btn-small" disabled={!!busy} onClick={() => derive({ type: "cleanup", min_area: tool.min_area, smooth: true }, "Line cleanup")}>Apply cleanup</button>
                <div className="row gap wrap">
                  <button className={`btn btn-small ${mode === "erase" ? "btn-primary" : ""}`} disabled={!!(+selEl.rotation)} onClick={() => { setMode(mode === "erase" ? "select" : "erase"); setEraseShapes([]); }}>
                    {mode === "erase" ? "Exit eraser" : "Eraser (drag boxes)"}
                  </button>
                  {mode === "erase" && eraseShapes.length > 0 && (
                    <button className="btn btn-small btn-primary" onClick={async () => { await derive({ type: "erase", shapes: eraseShapes.map(({ shape, x, y, w, h }) => ({ shape, x, y, w, h })) }, "Erase"); setEraseShapes([]); setMode("select"); }}>
                      Apply {eraseShapes.length} erase box{eraseShapes.length > 1 ? "es" : ""}
                    </button>
                  )}
                </div>
                {!!(+selEl.rotation) && <p className="muted small">Set rotation to 0 to use the eraser.</p>}
                <button className="btn btn-small btn-ghost" disabled={!!busy} onClick={() => confirm("Enlarging (2×) makes a bigger file but does NOT create genuine detail. Preflight will keep judging resolution by the original pixels. Continue?") && derive({ type: "upscale", factor: 2 }, "Enlarge 2×")}>
                  Enlarge 2× (no new detail)
                </button>
                {busy && <Loading what={busy} />}
                <div className="row gap wrap">
                  <button className="btn btn-small" onClick={showAsset}>Versions & provenance</button>
                </div>
              </>
            )}
            {selEl.kind === "text" && (
              <>
                <Field label="Text"><textarea rows={4} value={selEl.text} onChange={(e) => update(selEl.id, { text: e.target.value })} /></Field>
                <div className="grid2">
                  <Field label="Size (pt)"><input type="number" min={6} max={150} value={selEl.size_pt} onChange={(e) => update(selEl.id, { size_pt: +e.target.value })} /></Field>
                  <Field label="Align"><select value={selEl.align || "left"} onChange={(e) => update(selEl.id, { align: e.target.value })}><option>left</option><option>center</option><option>right</option></select></Field>
                </div>
                <label className="check-inline"><input type="checkbox" checked={!!selEl.bold} onChange={(e) => update(selEl.id, { bold: e.target.checked })} /> Bold</label>
                <p className="muted small">Font: DejaVu Sans (free license, embedded in the PDF).</p>
              </>
            )}
            <h4>Align to safe area</h4>
            <div className="row gap wrap">
              {[["left", "⇤"], ["hcenter", "↔"], ["right", "⇥"], ["top", "⤒"], ["vcenter", "↕"], ["bottom", "⤓"]].map(([k, s]) => (
                <button key={k} className="btn btn-tiny" onClick={() => align(k)} aria-label={`Align ${k}`}>{s} {k}</button>
              ))}
            </div>
            <div className="row gap wrap">
              <button className="btn btn-small" onClick={() => { const i = els.findIndex((x) => x.id === sel); if (i < els.length - 1) { const n = [...els]; [n[i], n[i + 1]] = [n[i + 1], n[i]]; commit(n); } }}>Bring forward</button>
              <button className="btn btn-small" onClick={() => { const i = els.findIndex((x) => x.id === sel); if (i > 0) { const n = [...els]; [n[i], n[i - 1]] = [n[i - 1], n[i]]; commit(n); } }}>Send back</button>
              <button className="btn btn-small btn-ghost" onClick={() => { commit(els.filter((x) => x.id !== sel)); setSel(null); }}>Remove</button>
            </div>
          </div>
        )}
      </aside>

      {compare && (
        <Modal title={`Before / after – ${compare.label}`} onClose={() => setCompare(null)} wide>
          <div className="compare">
            <figure><img src={img(compare.before, 900)} alt="Before" /><figcaption>Before</figcaption></figure>
            <figure><img src={img(compare.after, 900)} alt="After" /><figcaption>After (new version)</figcaption></figure>
          </div>
          <div className="row gap end">
            <button className="btn" onClick={() => { update(compare.elId, { asset_version_id: compare.before }); setCompare(null); toast("info", "Reverted to the previous version (the new one stays in history)."); }}>Revert</button>
            <button className="btn btn-primary" onClick={() => setCompare(null)}>Keep change</button>
          </div>
        </Modal>
      )}
      {preview && (
        <Modal title="Exact print preview (same renderer as the PDF export)" onClose={() => setPreview(null)} wide>
          <img className="preview-img" src={preview} alt="Rendered page preview" />
        </Modal>
      )}
      {picker && <ArtPicker pid={pid} onClose={() => setPicker(false)} onPick={async (vid: string) => { await flush(); await api.post(`/api/pages/${pageId}/place`, { version_id: vid, fit: "safe" }); setPicker(false); setPast([]); setFuture([]); await load(); refresh(); }} />}
      {hist && (
        <Modal title="Page history" onClose={() => setHist(null)}>
          {hist.length === 0 && <p className="muted">No saved history yet.</p>}
          <ul className="hist">
            {hist.map((h) => (
              <li key={h.id}>
                {new Date(h.created_at).toLocaleString()} – {h.reason} ({h.element_count} items)
                <button className="btn btn-tiny" onClick={async () => { await flush(); await api.post(`/api/pages/${pageId}/restore/${h.id}`); setHist(null); await load(); toast("ok", "Restored. (The state before restoring is in history too.)"); }}>Restore</button>
              </li>
            ))}
          </ul>
        </Modal>
      )}
      {assetInfo && selEl && (
        <Modal title={`Versions – ${assetInfo.display_name}`} onClose={() => setAssetInfo(null)}>
          <p className="muted small">Provenance: {assetInfo.source_type} · AI: {assetInfo.ai_involvement} · rights: {assetInfo.rights_declaration}. Provenance applies to every version.</p>
          <ul className="hist">
            {assetInfo.versions.map((v: any) => (
              <li key={v.id}>
                <img src={img(v.id, 80)} alt="" /> v{v.version_no} – {v.operation?.type} {v.id === selEl.asset_version_id && <Badge kind="ok">in use</Badge>}
                {v.id !== selEl.asset_version_id && <button className="btn btn-tiny" onClick={() => { setVersions((x) => ({ ...x, [v.id]: v })); update(selEl.id, { asset_version_id: v.id }); setAssetInfo(null); }}>Use this version</button>}
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </div>
  );
}

function ArtPicker({ pid, onClose, onPick }: any) {
  const [list, setList] = useState<any[] | null>(null);
  useEffect(() => { api.get(`/api/projects/${pid}/assets?kind=artwork`).then(setList); }, [pid]);
  return (
    <Modal title="Choose artwork" onClose={onClose} wide>
      {!list && <Loading />}
      {list && list.length === 0 && <p>No artwork yet. Import files in <a href={`#/p/${pid}/artwork`}>Artwork</a>.</p>}
      <div className="asset-grid">
        {(list || []).map((a) => (
          <button key={a.id} className="card asset pick" onClick={() => onPick(a.current_version_id)}>
            <img src={img(a.current_version_id, 240)} alt="" loading="lazy" />
            <span className="asset-name">{a.display_name}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
}
