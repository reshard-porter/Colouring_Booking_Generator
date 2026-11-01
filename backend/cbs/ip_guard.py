"""Protected-name check (heuristic, NOT legal advice, NOT exhaustive).

Flags well-known character, team, franchise and studio names that an independent publisher
cannot use without a license. Matching is case-insensitive and tolerant of spaces/hyphens
("spider-man", "spider man", "spiderman"). Ambiguous everyday words are deliberately left out to
avoid false alarms, so a clean result does not mean a book is free of rights problems."""
from __future__ import annotations

import re
from functools import lru_cache

# (term, owner / franchise). Terms are written in lower case with spaces between words.
PROTECTED: list[tuple[str, str]] = [
    # DC / Warner Bros.
    ("justice league", "DC (Warner Bros. Discovery)"), ("superman", "DC (Warner Bros. Discovery)"),
    ("batman", "DC (Warner Bros. Discovery)"), ("wonder woman", "DC (Warner Bros. Discovery)"),
    ("aquaman", "DC (Warner Bros. Discovery)"), ("green lantern", "DC (Warner Bros. Discovery)"),
    ("the flash", "DC (Warner Bros. Discovery)"), ("martian manhunter", "DC (Warner Bros. Discovery)"),
    ("harley quinn", "DC (Warner Bros. Discovery)"), ("catwoman", "DC (Warner Bros. Discovery)"),
    ("supergirl", "DC (Warner Bros. Discovery)"), ("batgirl", "DC (Warner Bros. Discovery)"),
    ("teen titans", "DC (Warner Bros. Discovery)"), ("lex luthor", "DC (Warner Bros. Discovery)"),
    ("darkseid", "DC (Warner Bros. Discovery)"), ("shazam", "DC (Warner Bros. Discovery)"),
    ("gotham city", "DC (Warner Bros. Discovery)"), ("dc comics", "DC (Warner Bros. Discovery)"),
    ("dc super hero", "DC (Warner Bros. Discovery)"), ("krypto", "DC (Warner Bros. Discovery)"),
    # Marvel / Disney
    ("marvel", "Marvel (Disney)"), ("avengers", "Marvel (Disney)"), ("spider man", "Marvel (Disney)"),
    ("iron man", "Marvel (Disney)"), ("captain america", "Marvel (Disney)"),
    ("the hulk", "Marvel (Disney)"), ("incredible hulk", "Marvel (Disney)"), ("black panther", "Marvel (Disney)"),
    ("x men", "Marvel (Disney)"), ("deadpool", "Marvel (Disney)"), ("thanos", "Marvel (Disney)"),
    ("groot", "Marvel (Disney)"), ("guardians of the galaxy", "Marvel (Disney)"), ("doctor strange", "Marvel (Disney)"),
    ("ant man", "Marvel (Disney)"), ("scarlet witch", "Marvel (Disney)"), ("spidey", "Marvel (Disney)"),
    # Anime / manga
    ("naruto", "Masashi Kishimoto / Shueisha"), ("sasuke", "Masashi Kishimoto / Shueisha"),
    ("one piece anime", "Eiichiro Oda / Shueisha / Toei"), ("luffy", "Eiichiro Oda / Shueisha / Toei"),
    ("dragon ball", "Bird Studio / Shueisha / Toei"), ("goku", "Bird Studio / Shueisha / Toei"),
    ("vegeta", "Bird Studio / Shueisha / Toei"), ("pokemon", "The Pokémon Company / Nintendo"),
    ("pokémon", "The Pokémon Company / Nintendo"), ("pikachu", "The Pokémon Company / Nintendo"),
    ("sailor moon", "Naoko Takeuchi / Kodansha / Toei"), ("my hero academia", "Kohei Horikoshi / Shueisha"),
    ("demon slayer", "Koyoharu Gotouge / Shueisha"), ("tanjiro", "Koyoharu Gotouge / Shueisha"),
    ("nezuko", "Koyoharu Gotouge / Shueisha"), ("attack on titan", "Hajime Isayama / Kodansha"),
    ("jujutsu kaisen", "Gege Akutami / Shueisha"), ("chainsaw man", "Tatsuki Fujimoto / Shueisha"),
    ("spy x family", "Tatsuya Endo / Shueisha"), ("studio ghibli", "Studio Ghibli"), ("totoro", "Studio Ghibli"),
    ("spirited away", "Studio Ghibli"), ("hello kitty", "Sanrio"), ("sanrio", "Sanrio"), ("kuromi", "Sanrio"),
    ("doraemon", "Fujiko Pro / Shogakukan"), ("astro boy", "Tezuka Productions"), ("death note", "Shueisha"),
    ("one punch man", "ONE / Shueisha"), ("hunter x hunter", "Yoshihiro Togashi / Shueisha"),
    ("yu gi oh", "Konami / Shueisha"), ("digimon", "Bandai / Toei"), ("beyblade", "Takara Tomy"),
    ("jojo's bizarre", "Hirohiko Araki / Shueisha"),
    # Cartoons, games and toy brands
    ("mickey mouse", "Disney"), ("minnie mouse", "Disney"), ("disney", "Disney"), ("pixar", "Disney/Pixar"),
    ("spongebob", "Paramount / Nickelodeon"), ("paw patrol", "Spin Master"), ("peppa pig", "Hasbro / Entertainment One"),
    ("bluey", "Ludo Studio / BBC Studios"), ("scooby doo", "Warner Bros. Discovery"), ("looney tunes", "Warner Bros. Discovery"),
    ("bugs bunny", "Warner Bros. Discovery"), ("tom and jerry", "Warner Bros. Discovery"),
    ("powerpuff girls", "Warner Bros. Discovery / Cartoon Network"), ("teenage mutant ninja turtles", "Paramount / Nickelodeon"),
    ("ninja turtles", "Paramount / Nickelodeon"), ("tmnt", "Paramount / Nickelodeon"), ("transformers", "Hasbro"),
    ("optimus prime", "Hasbro"), ("sonic the hedgehog", "SEGA"), ("super mario", "Nintendo"), ("nintendo", "Nintendo"),
    ("minions", "Universal / Illumination"), ("shrek", "DreamWorks / Universal"), ("garfield", "Paws Inc. / Paramount"),
    ("snoopy", "Peanuts Worldwide"), ("barbie", "Mattel"), ("my little pony", "Hasbro"), ("care bears", "Cloudco"),
    ("smurfs", "IMPS / Peyo"), ("cartoon network", "Warner Bros. Discovery"), ("nickelodeon", "Paramount"),
    ("warner bros", "Warner Bros. Discovery"), ("lego", "The LEGO Group"), ("minecraft", "Mojang / Microsoft"),
    ("roblox", "Roblox Corporation"), ("fortnite", "Epic Games"), ("winnie the pooh", "Disney (later versions; early book text/art may be public domain – check carefully)"),
]


def _pattern(term: str) -> str:
    words = re.split(r"\s+", term.strip())
    return r"(?<![a-z0-9])" + r"[\s\-_.']*".join(re.escape(w) for w in words) + r"(?![a-z0-9])"


@lru_cache(maxsize=1)
def _compiled():
    out = []
    for term, owner in PROTECTED:
        out.append((term, owner, re.compile(_pattern(term), re.IGNORECASE)))
        if " " in term:  # also catch the joined form, e.g. "spiderman", "ironman"
            out.append((term, owner, re.compile(_pattern(term.replace(" ", "")), re.IGNORECASE)))
    return out


def find(text: str) -> list[dict]:
    if not text:
        return []
    hits, seen = [], set()
    for term, owner, rx in _compiled():
        m = rx.search(text)
        if m and term not in seen:
            seen.add(term)
            hits.append({"term": term, "matched": m.group(0), "owner": owner})
    return hits


def licensed_terms(listing: dict) -> dict[str, str]:
    """Owner-declared licenses: {'term': 'evidence'} — only honoured when evidence text is given."""
    out = {}
    for row in listing.get("licensed_terms") or []:
        term = (row.get("term") or "").strip().lower()
        ev = (row.get("evidence") or "").strip()
        if term and ev:
            out[term] = ev
    return out


def scan_project(snap: dict) -> list[dict]:
    """Return findings: {where, severity, term, owner, matched, page_id, page_number, licensed}."""
    listing, spec, style = snap["listing"], snap["spec"], snap.get("style_guide") or {}
    lic = licensed_terms(listing)
    sources: list[tuple[str, str, str, dict]] = []  # (where, severity, text, extra)
    for k in ("title", "subtitle", "author"):
        sources.append((f"book {k}", "error", spec.get(k) or "", {}))
        sources.append((f"listing {k}", "error", listing.get(k) or "", {}))
    sources.append(("listing description", "error", listing.get("description") or "", {}))
    for kw in listing.get("keywords") or []:
        sources.append(("keywords", "error", kw or "", {}))
    cd = snap["cover"]["data"]
    for k in ("title", "subtitle", "author", "back_copy", "spine_text"):
        sources.append((f"cover {k.replace('_', ' ')}", "error", cd.get(k) or "", {}))
    for k in ("front_description", "back_description"):
        sources.append((f"{k.split('_')[0]} cover description", "warning", cd.get(k) or "", {}))
    for p in snap["assembly"]["pages"]:
        for el in p.get("elements", []):
            if el.get("kind") == "text":
                sources.append(("page text", "error", el.get("text") or "", {"page_id": p.get("page_id"), "page_number": p["number"]}))
        if p.get("label"):
            sources.append(("page label", "warning", p["label"], {"page_id": p.get("page_id"), "page_number": p["number"]}))
    for i, s in enumerate(snap.get("scenes") or []):
        txt = " ".join(str(s.get(k) or "") for k in ("subject", "action", "setting", "composition", "notes", "description"))
        sources.append((f"scene #{i + 1}", "warning", txt, {"scene_id": s.get("id")}))
    for c in style.get("characters") or []:
        txt = " ".join(str(c.get(k) or "") for k in ("name", "appearance", "costume", "emblem", "powers"))
        sources.append((f"character “{c.get('name') or 'unnamed'}”", "warning", txt, {}))
    team = style.get("team") or {}
    sources.append(("hero team", "warning", " ".join(str(team.get(k) or "") for k in ("name", "motto", "headquarters", "emblem")), {}))
    for a in (snap.get("assets") or {}).values():
        sources.append(("artwork file name", "warning", a.get("display_name") or "", {}))
    out = []
    for where, sev, text, extra in sources:
        for h in find(text):
            licensed = h["term"] in lic
            out.append({"where": where, "severity": "review" if licensed else sev, "licensed": licensed,
                        "license_evidence": lic.get(h["term"]), **h, **extra})
    return out
