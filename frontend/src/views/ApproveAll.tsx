import React, { useState } from "react";
import { api } from "../api";
import { Loading, Modal, useToast } from "../ui";

/** One button that declares rights for the book's artwork and approves every illustration page that has art. */
export function ApproveAll({ pid, author, onDone, small }: { pid: string; author?: string; onDone: () => void; small?: boolean }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [checked, setChecked] = useState(false);
  const [creator, setCreator] = useState(author || "");
  const [ai, setAi] = useState("leave");
  const [busy, setBusy] = useState(false);
  async function start() {
    setOpen(true); setChecked(false); setPlan(null);
    try { setPlan(await api.get(`/api/projects/${pid}/approve-all`)); } catch (e: any) { toast("err", e.message); setOpen(false); }
  }
  async function go() {
    setBusy(true);
    try {
      const r = await api.post(`/api/projects/${pid}/approve-all`, { confirm: true, creator, ai_for_unknown: ai });
      toast("ok", `Approved ${r.pages_approved} page(s); rights declared for ${r.rights_declared} artwork file(s).`);
      setOpen(false); onDone();
    } catch (e: any) { toast("err", e.message); } finally { setBusy(false); }
  }
  async function undo() {
    if (!confirm("Remove the approval from every illustration page? (Rights declarations stay as they are.)")) return;
    const r = await api.post(`/api/projects/${pid}/unapprove-all`);
    toast("info", `${r.pages_unapproved} page approval(s) removed.`); setOpen(false); onDone();
  }
  const nothing = plan && plan.pages_to_approve === 0 && plan.rights_to_declare === 0 && plan.artwork_to_approve === 0;
  return (
    <>
      <button className={`btn ${small ? "btn-small" : ""}`} onClick={start}>✓ Approve everything…</button>
      {open && (
        <Modal title="Approve everything in this book" onClose={() => setOpen(false)}>
          {!plan && <Loading what="Checking the book" />}
          {plan && (
            <>
              <p>This will, in one step:</p>
              <ul>
                <li>approve <strong>{plan.pages_to_approve}</strong> illustration page(s){plan.pages_already_approved ? ` (${plan.pages_already_approved} already approved)` : ""}</li>
                <li>declare that you own or may sell <strong>{plan.rights_to_declare}</strong> artwork file(s) whose rights aren't declared yet</li>
                <li>mark <strong>{plan.artwork_to_approve}</strong> unreviewed artwork file(s) as approved</li>
              </ul>
              {plan.ai_generated > 0 && <p className="small note">{plan.ai_generated} artwork file(s) are recorded as AI-generated and stay that way – you still disclose them to KDP.</p>}
              {plan.ai_unknown > 0 && (
                <label className="block small">How were the {plan.ai_unknown} file(s) with unknown AI use made?{" "}
                  <select value={ai} onChange={(e) => setAi(e.target.value)}>
                    <option value="leave">Leave unknown (decide later)</option>
                    <option value="none">Made without AI</option>
                    <option value="ai_assisted">AI-assisted (I made them, AI helped)</option>
                    <option value="ai_generated">AI-generated</option>
                  </select>
                </label>
              )}
              {plan.rights_to_declare > 0 && (
                <label className="block small">Creator / rights holder <input value={creator} onChange={(e) => setCreator(e.target.value)} placeholder="Your name or pen name" /></label>
              )}
              {(plan.pages_without_art.length > 0 || plan.demo_art.length > 0 || plan.flagged.length > 0) && (
                <div className="warn-list small">
                  <p><strong>Not included:</strong></p>
                  <ul>
                    {plan.pages_without_art.length > 0 && <li>{plan.pages_without_art.length} page(s) without artwork yet</li>}
                    {plan.demo_art.length > 0 && <li>{plan.demo_art.length} demonstration sample drawing(s) – replace them with your own art</li>}
                    {plan.flagged.length > 0 && <li>{plan.flagged.length} artwork file(s) you marked “needs changes” or “rejected”</li>}
                  </ul>
                </div>
              )}
              <label className="row gap small check-confirm">
                <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
                <span>I have looked at every page, and I have the right to sell this artwork (my own work, AI images I generated under the provider's terms, or licensed art).</span>
              </label>
              <div className="row gap end wrap">
                {plan.pages_already_approved > 0 && <button className="btn btn-ghost btn-small" onClick={undo}>Take back page approvals</button>}
                <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
                <button className="btn btn-primary" disabled={!checked || busy || nothing} onClick={go}>{nothing ? "Nothing left to approve" : busy ? "Approving…" : "Approve everything"}</button>
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
