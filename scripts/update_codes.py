#!/usr/bin/env python3
"""
SpriteDex Fortnite Override code watcher.

Design:
- Keeps existing confirmed codes and reward metadata.
- Scans maintained public Fortnite code sources plus a dynamic Reddit search.
- Normalizes code candidates case-insensitively.
- A brand-new candidate seen in 2+ independent sources becomes confirmed.
- A brand-new candidate seen in only 1 source is retained as unverified.
- Never deletes an existing code just because a source is temporarily unavailable.
- Updates codes.json only when data materially changes.
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "codes.json"

STATIC_SOURCES = [
    ("reddit-o2-thread", "https://www.reddit.com/r/FortniteBR/comments/1vo4bwf/o2_is_collabing_with_fortnite_again_this_time/.json?raw_json=1"),
    ("reddit-all-known", "https://www.reddit.com/r/FortniteXPMaps/comments/1vth12e/all_known_lobby_hacks/.json?raw_json=1"),
    ("reddit-19-codes", "https://www.reddit.com/r/FortniteBR/comments/1vtj0yi/hello_guys_these_are_19_admin_panel_codes_enjoy/.json?raw_json=1"),
    ("nerdschalk", "https://nerdschalk.com/fortnite-override-codes/"),
]
REDDIT_SEARCHES = [
    "Fortnite Override code",
    "Fortnite lobby hack code",
    "Fortnite admin panel code",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SpriteDexCodeBot/1.0; +https://github.com/mrawlz17/SpriteDex)"
}

# Reject common prose tokens that otherwise look like codes.
STOPWORDS = {
    "FORTNITE","OVERRIDE","CHAPTER","SEASON","SPRITE","SPRITES","MASTER","CHEAT",
    "LOBBY","HACK","CODES","CODE","ADMIN","PANEL","REWARD","REWARDS","LOADING",
    "SCREEN","SCREENS","CURRENT","KNOWN","WORKING","AVAILABLE","TWITTER","REDDIT",
    "NINTENDO","SONIC","TAILS","TETRIS","PERSONA","XBOX","ALIENWARE","GENO",
    "THURSDAY","AUGUST","COMMENTS","COMMENT","THANK","THANKS","UNKNOWN","IMAGE",
    "UPDATE","UPDATED","COLLAB","COLLABS","COLLABORATION","REVEALS","REVEAL",
}
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{4,23})(?![A-Za-z0-9])")

def norm(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()

def plausible(token: str) -> bool:
    n = norm(token)
    if len(n) < 5 or len(n) > 24 or n in STOPWORDS:
        return False
    if n.isalpha() and n.lower() == token.lower():
        # Plain dictionary-like words are noisy; require code context elsewhere.
        return True
    return True

def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r

def walk_reddit(node, out: list[str]) -> None:
    if isinstance(node, dict):
        data = node.get("data") if isinstance(node.get("data"), dict) else None
        if data:
            for key in ("title", "selftext", "body"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    out.append(value)
        for value in node.values():
            walk_reddit(value, out)
    elif isinstance(node, list):
        for value in node:
            walk_reddit(value, out)

def strong_line_candidates(raw_line: str) -> set[str]:
    line = html.unescape(raw_line).strip()
    found: set[str] = set()
    if not line:
        return found

    # Markdown backticks or quoted values are strong code signals.
    for token in re.findall(r"[`\"]([A-Za-z][A-Za-z0-9]{4,23})[`\"]", line):
        if plausible(token):
            found.add(norm(token))

    # Explicit phrases such as "code PLAY4ALL".
    for token in re.findall(r"\bcode\s+[`\"]?([A-Za-z][A-Za-z0-9]{4,23})", line, re.I):
        if plausible(token):
            found.add(norm(token))

    # Standalone/list entries, optionally followed by a reward separator or parenthetical source.
    cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
    match = re.match(
        r"^([A-Za-z][A-Za-z0-9]{4,23})(?:\s*(?:->|—|-|:)\s*.+|\s+\([^)]*\))?$",
        cleaned,
    )
    if match and plausible(match.group(1)):
        found.add(norm(match.group(1)))
    return found

def candidates_from_reddit_json(payload) -> set[str]:
    texts: list[str] = []
    walk_reddit(payload, texts)
    found = set()
    for text in texts:
        for raw_line in text.splitlines():
            found.update(strong_line_candidates(raw_line))
    return found

def candidates_from_html(text: str) -> set[str]:
    soup = BeautifulSoup(text, "html.parser")
    found = set()
    # <code> tags are the strongest signal on guide sites.
    for tag in soup.find_all("code"):
        token = tag.get_text(" ", strip=True)
        if TOKEN_RE.fullmatch(token or "") and plausible(token):
            found.add(norm(token))
    # Also inspect short list/table rows mentioning code/reward.
    for tag in soup.find_all(["li", "tr", "p"]):
        text = " ".join(tag.stripped_strings)
        if len(text) > 180:
            continue
        if not any(k in text.lower() for k in ("code", "sprite", "dust", "xp", "locator", "loading screen", "override")):
            continue
        for token in TOKEN_RE.findall(text):
            if plausible(token):
                found.add(norm(token))
    return found

def scan_source(name: str, url: str) -> set[str]:
    response = fetch(url)
    ctype = response.headers.get("content-type", "")
    if "json" in ctype or url.endswith(".json?raw_json=1"):
        return candidates_from_reddit_json(response.json())
    return candidates_from_html(response.text)

def scan_dynamic_reddit() -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for query in REDDIT_SEARCHES:
        url = "https://www.reddit.com/search.json?q=" + quote(query) + "&sort=new&t=week&limit=35&raw_json=1"
        try:
            payload = fetch(url).json()
            # Treat each search query as one discovery source.
            hits["reddit-search:" + query] = candidates_from_reddit_json(payload)
        except Exception as exc:
            print(f"Warning: Reddit search failed for {query!r}: {exc}", file=sys.stderr)
    return hits

def main() -> int:
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing = {norm(item["code"]): item for item in current.get("codes", [])}
    sightings: dict[str, set[str]] = defaultdict(set)

    successful_sources = 0
    for name, url in STATIC_SOURCES:
        try:
            found = scan_source(name, url)
            successful_sources += 1
            for code in found:
                sightings[code].add(name)
            print(f"{name}: {len(found)} candidates")
        except Exception as exc:
            print(f"Warning: {name} failed: {exc}", file=sys.stderr)

    dynamic = scan_dynamic_reddit()
    for name, found in dynamic.items():
        if found:
            successful_sources += 1
        for code in found:
            sightings[code].add(name)

    if successful_sources < 2:
        print("Safety stop: fewer than two sources were reachable.", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    changed = False

    # Existing codes are never removed. Refresh sightings/source state.
    for code_key, item in existing.items():
        if code_key in sightings:
            new_last = today
            if item.get("lastSeen") != new_last:
                item["lastSeen"] = new_last
                changed = True
            seen_sources = sorted(sightings[code_key])
            if item.get("observedSources") != seen_sources:
                item["observedSources"] = seen_sources
                changed = True

    # Add newly discovered candidates conservatively.
    for code_key, sources in sorted(sightings.items()):
        if code_key in existing:
            continue
        # Filter obvious noise more aggressively for unknown candidates.
        if code_key in STOPWORDS or len(code_key) < 6:
            continue
        status = "confirmed" if len(sources) >= 2 else "unverified"
        item = {
            "id": code_key,
            "code": code_key,
            "reward": "Reward not yet identified",
            "category": "Unknown",
            "status": status,
            "firstSeen": today,
            "lastSeen": today,
            "observedSources": sorted(sources),
        }
        current.setdefault("codes", []).append(item)
        existing[code_key] = item
        changed = True
        print(f"Discovered {code_key} ({status}; {len(sources)} source(s))")

    current["codes"] = sorted(
        current.get("codes", []),
        key=lambda x: (x.get("status") == "unverified", x.get("category", ""), x.get("code", ""))
    )

    if not changed:
        print("No code database changes.")
        return 0

    current["updated"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    current["databaseVersion"] = now.strftime("%Y.%m.%d.%H%M")
    DATA_FILE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {DATA_FILE.name}: {len(current['codes'])} codes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
