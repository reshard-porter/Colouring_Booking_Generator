import React, { useContext, useEffect, useState } from "react";
import { api } from "../api";
import { ProjectCtx } from "../App";
import { ErrorBox, Field, useToast } from "../ui";

export default function Pricing() {
  const { proj, refresh } = useContext(ProjectCtx);
  const pid = proj.project.id;
  const [price, setPrice] = useState(proj.listing.list_price || "9.99");
  const [sc, setSc] = useState({ copies: 50, ad_cost_per_sale: "0", artwork_costs: "0", proof_costs: "0", other_costs: "0" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const toast = useToast();
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        setRes(await api.post(`/api/projects/${pid}/pricing`, { list_price: price, scenario: sc }));
        setErr(null);
      } catch (e) {
        setErr(e);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [price, sc, pid]);
  const s = (k: string) => (e: any) => setSc({ ...sc, [k]: k === "copies" ? +e.target.value : e.target.value });
  return (
    <div className="page">
      <h1>Pricing calculator</h1>
      <p className="lede">Estimated royalty = royalty rate × tax-exclusive list price − printing cost. These are estimates from a dated reference profile, not live Amazon data.</p>
      <div className="split">
        <section className="card form-grid">
          <Field label={`List price (${res?.currency || "USD"}, tax-exclusive)`}><input type="number" step="0.01" min="0.01" value={price} onChange={(e) => setPrice(e.target.value)} /></Field>
          <div className="row gap">
            <button className="btn btn-small" onClick={() => setPrice("9.98")}>9.98</button>
            <button className="btn btn-small" onClick={() => setPrice("9.99")}>9.99</button>
            <button className="btn btn-small" onClick={async () => { await api.put(`/api/projects/${pid}/listing`, { ...proj.listing, list_price: price }); refresh(); toast("ok", "Saved as the listing price."); }}>Save as listing price</button>
          </div>
          <ErrorBox error={err} />
          {res && (
            <dl className="facts big">
              <dt>Interior pages</dt><dd>{res.page_count} ({res.trim_category} trim)</dd>
              <dt>Printing cost</dt><dd>{res.currency} {res.printing_cost}</dd>
              <dt>Royalty rate</dt><dd>{(+res.royalty_rate * 100).toFixed(0)}%</dd>
              <dt>Estimated royalty per copy</dt><dd className={res.royalty_negative ? "warn-text" : "ok-text"}><strong>{res.currency} {res.royalty_per_copy}</strong></dd>
            </dl>
          )}
          {res?.warning && <p className="warn-text">{res.warning}</p>}
          <p className="muted small">Expanded Distribution: {res?.expanded_distribution?.enabled ? "enabled" : "not included"} – {res?.expanded_distribution?.note}</p>
        </section>
        <section className="card form-grid">
          <h2>Scenario (your numbers)</h2>
          <Field label="Copies sold"><input type="number" min={0} value={sc.copies} onChange={s("copies")} /></Field>
          <Field label="Advertising cost per sale"><input type="number" step="0.01" value={sc.ad_cost_per_sale} onChange={s("ad_cost_per_sale")} /></Field>
          <Field label="Artwork costs (total)"><input type="number" step="0.01" value={sc.artwork_costs} onChange={s("artwork_costs")} /></Field>
          <Field label="Proof copies (total)"><input type="number" step="0.01" value={sc.proof_costs} onChange={s("proof_costs")} /></Field>
          <Field label="Other expenses"><input type="number" step="0.01" value={sc.other_costs} onChange={s("other_costs")} /></Field>
          {res?.scenario && (
            <dl className="facts">
              <dt>Customer sales revenue</dt><dd>{res.scenario.customer_sales_revenue} <span className="muted small">(what customers pay; not your income)</span></dd>
              <dt>Your royalties</dt><dd>{res.scenario.royalties}</dd>
              <dt>Advertising</dt><dd>−{res.scenario.advertising}</dd>
              <dt>Fixed costs</dt><dd>−{res.scenario.fixed_costs}</dd>
              <dt>Estimated profit</dt><dd><strong>{res.scenario.estimated_profit}</strong></dd>
              <dt>Break-even copies</dt><dd>{res.scenario.break_even_copies ?? "never at this ad cost"}</dd>
            </dl>
          )}
          <p className="muted small">{res?.scenario?.disclaimer} Totals use exact per-copy amounts; per-copy figures are rounded to cents for display.</p>
        </section>
      </div>
      {res && (
        <section className="card">
          <h2>Active profile</h2>
          <p>{res.marketplace} · {res.currency} · profile <code>{res.profile_id}</code> · checked {res.checked_on}</p>
          <p className="muted small">{res.note}</p>
          <ul className="small">
            {Object.entries(res.sources).map(([k, u]: any) => <li key={k}>{k.replace(/_/g, " ")}: <a href={u} target="_blank" rel="noreferrer">{u}</a></li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
