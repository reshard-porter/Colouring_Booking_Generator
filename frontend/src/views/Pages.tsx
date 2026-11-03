import React, { useContext, useState } from "react";
import { api, img } from "../api";
import { ProjectCtx, go } from "../App";
import { Badge, useToast } from "../ui";
import { ApproveAll } from "./ApproveAll";

export default function Pages() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const toast = useToast();
  const [dragId, setDragId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pagesById: Record<string, any> = Object.fromEntries(proj.pages.map((p: any) => [p.id, p]));
  const asm = proj.assembly;
  const content = proj.pages.map((p: any) => p.id);

  async function act(fn: () => Promise<any>, msg?: string) {
    setBusy(true);
    try {
      await fn();
      await refresh();
      if (msg) toast("ok", msg);
    } catch (e: any) {
      toast("err", e.message);
    } finally {
      setBusy(false);
    }
  }
  function move(id: string, delta: number) {
    const order = [...content];
    const i = order.indexOf(id);
    const kind = pagesById[id].kind;
    let j = i + delta;
    while (j >= 0 && j < order.length && pagesById[order[j]].kind !== kind) j += delta;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    act(() => api.post(`/api/projects/${pid}/pages/reorder`, { order }), "Page order updated. Blank backs follow automatically.");
  }
  function drop(targetId: string) {
    if (!dragId || dragId === targetId) return;
    if (pagesById[dragId].kind !== pagesById[targetId].kind) {
      toast("err", "Intro pages stay before illustrations.");
      return;
    }
    const order = content.filter((x: string) => x !== dragId);
    order.splice(order.indexOf(targetId), 0, dragId);
    act(() => api.post(`/api/projects/${pid}/pages/reorder`, { order }), "Page moved.");
  }
  const approvedCount = proj.pages.filter((p: any) => p.kind === "illustration" && p.approved).length;

  return (
    <div className="page">
      <div className="row between">
        <div>
          <h1>Pages & layout</h1>
          <p className="lede">
            {asm.page_count} interior pages: {asm.intro_count} intro, {asm.illustration_count} illustrations on right-hand pages, {asm.blank_count} blank. Single pages, not spreads.
          </p>
        </div>
        <div className="row gap">
          <ApproveAll pid={pid} author={proj.spec.author} onDone={refresh} />
          <button className="btn" disabled={busy} onClick={() => act(() => api.post(`/api/projects/${pid}/pages`, { kind: "intro" }), "Intro page added.")}>+ Intro page</button>
          <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.post(`/api/projects/${pid}/pages`, { kind: "illustration" }), "Illustration page added.")}>+ Illustration page</button>
        </div>
      </div>
      {proj.cover.stale && (
        <div className="banner banner-bad" role="alert">
          The page count changed, so the cover size is out of date. {proj.cover.stale_reasons.join(" ")} <a href={`#/p/${pid}/cover`}>Recalculate the cover</a>.
        </div>
      )}
      {asm.parity_notes.map((n: string) => <div key={n} className="banner banner-info">{n}</div>)}
      <p className="muted">Approved illustrations: {approvedCount} / {asm.illustration_count}. Drag cards (or use the arrows) to reorder; editing a page clears its approval.</p>
      <div className="book-grid" aria-label="Book pages in print order">
        {asm.pages.map((e: any) => {
          const p = e.page_id ? pagesById[e.page_id] : null;
          const imgEl = p?.elements.find((x: any) => x.kind === "image");
          return (
            <div
              key={e.number}
              className={`pcard pcard-${e.kind} ${e.side}`}
              draggable={!!p}
              onDragStart={() => p && setDragId(p.id)}
              onDragOver={(ev) => p && ev.preventDefault()}
              onDrop={() => p && drop(p.id)}
            >
              <div className="pcard-num">
                {e.number} <span className="muted small">{e.side === "recto" ? "right" : "left"}</span>
              </div>
              <div className="pcard-thumb" onClick={() => p && go(`/p/${pid}/editor/${p.id}`)} role={p ? "button" : undefined} tabIndex={p ? 0 : -1}
                onKeyDown={(k) => p && k.key === "Enter" && go(`/p/${pid}/editor/${p.id}`)} aria-label={p ? `Edit ${p.label}` : `Blank page ${e.number}`}>
                {e.kind === "story" && <span className="intro-text small" onClick={(ev) => { ev.stopPropagation(); go(`/p/${pid}/descriptions`); }}>story text for the picture on the right ✎</span>}
                {e.kind === "blank" && <span className="muted small">{e.blank_reason === "back" ? "blank back" : e.blank_reason === "parity" ? "parity blank (auto)" : "end blank (auto)"}</span>}
                {imgEl && <img src={img(imgEl.asset_version_id, 200)} alt="" loading="lazy" />}
                {p && !imgEl && e.kind === "illustration" && <span className="warn-text small">no artwork</span>}
                {p && e.kind === "intro" && <span className="intro-text small">{p.elements.find((x: any) => x.kind === "text")?.text?.slice(0, 60) || p.label}</span>}
              </div>
              {p && (
                <>
                  <div className="pcard-label" title={p.label}>{p.label}</div>
                  <div className="row gap wrap pcard-actions">
                    {p.kind === "illustration" && (
                      <button className={`btn btn-tiny ${p.approved ? "btn-ok" : ""}`} aria-pressed={p.approved}
                        onClick={() => act(() => api.post(`/api/pages/${p.id}/approve`, { approved: !p.approved }))}>
                        {p.approved ? "✓ Approved" : "Approve"}
                      </button>
                    )}
                    <button className="btn btn-tiny" aria-label="Move earlier" onClick={() => move(p.id, -1)}>↑</button>
                    <button className="btn btn-tiny" aria-label="Move later" onClick={() => move(p.id, 1)}>↓</button>
                    <button className="btn btn-tiny" onClick={() => act(() => api.post(`/api/pages/${p.id}/duplicate`), "Page duplicated.")}>Duplicate</button>
                    <button className="btn btn-tiny btn-ghost" onClick={() => confirm(`Delete “${p.label}”? Its blank back is removed too.`) && act(() => api.del(`/api/pages/${p.id}`), "Page deleted.")}>Delete</button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
