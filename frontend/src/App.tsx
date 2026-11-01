import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Badge, ErrorBox, Loading } from "./ui";
import Dashboard from "./views/Dashboard";
import Setup from "./views/Setup";
import Plan from "./views/Plan";
import Artwork from "./views/Artwork";
import Pages from "./views/Pages";
import Editor from "./views/Editor";
import Cover from "./views/Cover";
import Preflight from "./views/Preflight";
import Pricing from "./views/Pricing";
import Listing from "./views/Listing";
import Export from "./views/Export";
import Promo from "./views/Promo";
import Settings from "./views/Settings";
import AutoBook from "./views/AutoBook";
import PageDescriptions from "./views/PageDescriptions";

export type Route = { name: string; pid?: string; arg?: string };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "p" && parts[1]) return { name: parts[2] || "setup", pid: parts[1], arg: parts[3] };
  if (parts[0] === "settings") return { name: "settings" };
  return { name: "home" };
}

export function go(r: string) {
  window.location.hash = r;
}

export const ProjectCtx = React.createContext<{ proj: any; refresh: () => Promise<any> }>({ proj: null, refresh: async () => {} });

const STEPS: [string, string, string][] = [
  ["auto", "✨", "Create with AI"],
  ["descriptions", "✎", "Page descriptions"],
  ["setup", "1", "Book setup"],
  ["plan", "2", "Plan & style"],
  ["artwork", "3", "Artwork"],
  ["pages", "4", "Pages & layout"],
  ["cover", "5", "Cover"],
  ["preflight", "6", "Preflight"],
  ["pricing", "7", "Pricing"],
  ["listing", "8", "Listing & disclosure"],
  ["export", "9", "Export package"],
  ["promo", "+", "Promo video"],
];

export default function App() {
  const [route, setRoute] = useState<Route>(parse(window.location.hash));
  const [proj, setProj] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  useEffect(() => {
    const h = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  const refresh = useCallback(async () => {
    if (!route.pid) return null;
    try {
      const p = await api.get(`/api/projects/${route.pid}`);
      setProj(p);
      setErr(null);
      return p;
    } catch (e) {
      setErr(e);
    }
  }, [route.pid]);
  useEffect(() => {
    setProj(null);
    refresh();
  }, [route.pid]);

  if (!route.pid) {
    return (
      <div className="shell shell-home">
        <TopBar />
        <main className="main" id="main">
          {route.name === "settings" ? <Settings /> : <Dashboard />}
        </main>
      </div>
    );
  }
  const counts = proj?.assembly;
  const pf = proj?.preflight_summary;
  return (
    <ProjectCtx.Provider value={{ proj, refresh }}>
      <div className="shell">
        <TopBar title={proj?.spec?.title} sample={proj?.project?.is_sample} />
        <nav className="side" aria-label="Book workflow">
          <a className="side-back" href="#/">
            ← All projects
          </a>
          {STEPS.map(([key, num, label]) => (
            <a key={key} href={`#/p/${route.pid}/${key}`} className={`side-link ${route.name === key || (key === "pages" && route.name === "editor") ? "active" : ""}`}>
              <span className="side-num">{num}</span>
              <span>{label}</span>
              {key === "pages" && counts && <span className="side-meta">{counts.page_count}p</span>}
              {key === "cover" && proj?.cover?.stale && <Badge kind="bad">stale</Badge>}
              {key === "preflight" && pf && <Badge kind={pf.counts.error ? "bad" : pf.counts.review ? "review" : "ok"}>{pf.counts.error ? `${pf.counts.error} err` : pf.counts.review ? "review" : "pass"}</Badge>}
            </a>
          ))}
          <div className="side-foot">
            <p>Files are prepared here. You upload them to KDP yourself.</p>
          </div>
        </nav>
        <main className="main" id="main">
          <ErrorBox error={err} retry={refresh} />
          {!proj && !err && <Loading what="Opening project" />}
          {proj && <View route={route} />}
        </main>
      </div>
    </ProjectCtx.Provider>
  );
}

function View({ route }: { route: Route }) {
  switch (route.name) {
    case "auto": return <AutoBook />;
    case "descriptions": return <PageDescriptions />;
    case "plan": return <Plan />;
    case "artwork": return <Artwork />;
    case "pages": return <Pages />;
    case "editor": return <Editor pageId={route.arg!} key={route.arg} />;
    case "cover": return <Cover />;
    case "preflight": return <Preflight />;
    case "pricing": return <Pricing />;
    case "listing": return <Listing />;
    case "export": return <Export />;
    case "promo": return <Promo />;
    default: return <Setup />;
  }
}

function TopBar({ title, sample }: { title?: string; sample?: boolean }) {
  return (
    <header className="top">
      <a className="skip" href="#main">Skip to content</a>
      <a className="brand" href="#/">
        <span className="brand-mark" aria-hidden>◎</span> Coloring Book Studio
      </a>
      {title && (
        <span className="top-title">
          {title} {sample ? <Badge kind="review">sample project · demo art</Badge> : null}
        </span>
      )}
      <a className="top-link" href="#/settings">Settings</a>
    </header>
  );
}
