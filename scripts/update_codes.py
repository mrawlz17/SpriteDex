#!/usr/bin/env python3
"""Conservative Fortnite Override code watcher for SpriteDex V32.0.

Safety rules:
- Existing codes are never deleted because a source is temporarily unavailable.
- Reddit search results are deduplicated by actual post ID; multiple search queries
  cannot make one post look like multiple independent sources.
- New codes remain Unverified until two independent sources have reported them.
- Existing Unverified codes are automatically promoted once corroborated.
- A code is marked Expired only after two independent sources explicitly describe
  it as expired/disabled/not working. Absence from a source never expires a code.
- An expired code can return to Active after two independent active sightings with
  no current expiry sightings.
- Reward text is only filled automatically when two independent sources agree.
- If fewer than two source endpoints are reachable, the run exits without writing.
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
    ("reddit-post:1vo4bwf", "https://www.reddit.com/r/FortniteBR/comments/1vo4bwf/o2_is_collabing_with_fortnite_again_this_time/.json?raw_json=1", "reddit"),
    ("reddit-post:1vth12e", "https://www.reddit.com/r/FortniteXPMaps/comments/1vth12e/all_known_lobby_hacks/.json?raw_json=1", "reddit"),
    ("reddit-post:1vtj0yi", "https://www.reddit.com/r/FortniteBR/comments/1vtj0yi/hello_guys_these_are_19_admin_panel_codes_enjoy/.json?raw_json=1", "reddit"),
    ("site:nerdschalk", "https://nerdschalk.com/fortnite-override-codes/", "html"),
]
REDDIT_SEARCHES = [
    "Fortnite Override code",
    "Fortnite lobby hack code",
    "Fortnite admin panel code",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SpriteDexCodeBot/2.0; +https://github.com/mrawlz17/SpriteDex)"}

STOPWORDS = {
    "FORTNITE","OVERRIDE","CHAPTER","SEASON","SPRITE","SPRITES","MASTER","CHEAT","LOBBY","HACK",
    "CODES","CODE","ADMIN","PANEL","REWARD","REWARDS","LOADING","SCREEN","SCREENS","CURRENT","KNOWN",
    "WORKING","AVAILABLE","TWITTER","REDDIT","NINTENDO","SONIC","TAILS","TETRIS","PERSONA","XBOX",
    "ALIENWARE","GENO","THURSDAY","AUGUST","COMMENTS","COMMENT","THANK","THANKS","UNKNOWN","IMAGE",
    "UPDATE","UPDATED","COLLAB","COLLABS","COLLABORATION","REVEALS","REVEAL","ACTIVE","EXPIRED","DISABLED",
}
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{5,24})(?![A-Za-z0-9])")
EXPIRED_RE = re.compile(r"\b(expired|disabled|deactivated|inactive|removed|no longer works?|not working|doesn['’]?t work|stopped working)\b", re.I)
LEGACY_SOURCE_MAP = {
    "reddit-o2-thread": "reddit-post:1vo4bwf",
    "reddit-all-known": "reddit-post:1vth12e",
    "reddit-19-codes": "reddit-post:1vtj0yi",
    "nerdschalk": "site:nerdschalk",
}


def norm(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def plausible(token: str) -> bool:
    n = norm(token)
    return 5 <= len(n) <= 24 and n not in STOPWORDS and any(ch.isalpha() for ch in n)


def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r


def canonical_historical_sources(values) -> set[str]:
    out = set()
    for value in values or []:
        value = LEGACY_SOURCE_MAP.get(str(value), str(value))
        # V31.1 counted search query names as sources. Those are intentionally
        # discarded because one Reddit post could appear in all three searches.
        if value.startswith("reddit-search:"):
            continue
        if value:
            out.add(value)
    return out


def strong_line_candidates(raw_line: str) -> set[str]:
    line = html.unescape(raw_line).strip()
    found: set[str] = set()
    if not line:
        return found
    for token in re.findall(r"[`\"]([A-Za-z0-9]{5,24})[`\"]", line):
        if plausible(token): found.add(norm(token))
    for token in re.findall(r"\bcode\s+[`\"]?([A-Za-z0-9]{5,24})", line, re.I):
        if plausible(token): found.add(norm(token))
    cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
    match = re.match(r"^([A-Za-z0-9]{5,24})(?:\s*(?:->|—|-|:|=)\s*.+|\s+\([^)]*\))?$", cleaned)
    if match and plausible(match.group(1)): found.add(norm(match.group(1)))
    return found


def known_codes_in_line(line: str, known_codes: set[str]) -> set[str]:
    upper = line.upper()
    return {code for code in known_codes if re.search(rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])", upper)}


def clean_reward(text: str) -> str | None:
    text = html.unescape(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^[\s\-–—:=>|()\[\]*`]+|[\s\-–—:=>|()\[\]*`]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > 120 or EXPIRED_RE.search(text): return None
    if text.lower() in {"code", "codes", "reward", "rewards"}: return None
    return text


def reward_from_line(line: str, code: str) -> str | None:
    m = re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", line, re.I)
    if not m: return None
    tail = line[m.end():]
    # Prefer an explicit separator after the code.
    sep = re.match(r"\s*(?:->|—|–|-|:|=)\s*(.+)$", tail)
    if sep: return clean_reward(sep.group(1))
    paren = re.match(r"\s*\(([^)]+)\)", tail)
    if paren: return clean_reward(paren.group(1))
    return None


def reward_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def infer_category(reward: str) -> str:
    r = reward.lower()
    if "sprite" in r: return "Cheat Master Sprite"
    if re.search(r"\bxp\b", r): return "XP"
    if "sprite dust" in r or " dust" in r: return "Sprite Dust"
    if "loading screen" in r: return "Loading Screen"
    if "lobby" in r or "tetris block" in r: return "Lobby Effect"
    if any(x in r for x in ("extractor", "accelerator", "locator", "taco", "supply drop")): return "Gizmo"
    return "Unknown"


def parse_lines(lines: list[str], known_codes: set[str]):
    active, expired = set(), set()
    rewards: dict[str, str] = {}
    for raw in lines:
        line = html.unescape(raw).strip()
        if not line: continue
        candidates = strong_line_candidates(line) | known_codes_in_line(line, known_codes)
        if not candidates: continue
        is_expired = bool(EXPIRED_RE.search(line))
        for code in candidates:
            (expired if is_expired else active).add(code)
            if not is_expired:
                reward = reward_from_line(line, code)
                if reward: rewards[code] = reward
    return active, expired, rewards


def walk_reddit(node, out: list[str]) -> None:
    if isinstance(node, dict):
        data = node.get("data") if isinstance(node.get("data"), dict) else None
        if data:
            for key in ("title", "selftext", "body"):
                value = data.get(key)
                if isinstance(value, str) and value: out.extend(value.splitlines())
        for value in node.values(): walk_reddit(value, out)
    elif isinstance(node, list):
        for value in node: walk_reddit(value, out)


def scan_reddit_payload(payload, known_codes: set[str]):
    lines: list[str] = []
    walk_reddit(payload, lines)
    return parse_lines(lines, known_codes)


def scan_html(text: str, known_codes: set[str]):
    soup = BeautifulSoup(text, "html.parser")
    lines: list[str] = []
    for tag in soup.find_all("code"):
        value = tag.get_text(" ", strip=True)
        if value: lines.append(value)
        parent = tag.parent.get_text(" ", strip=True) if tag.parent else ""
        if parent and len(parent) <= 220: lines.append(parent)
    for tag in soup.find_all(["li", "tr", "p"]):
        value = " ".join(tag.stripped_strings)
        if value and len(value) <= 220 and any(k in value.lower() for k in ("code", "sprite", "dust", "xp", "locator", "loading screen", "override", "expired", "working")):
            lines.append(value)
    return parse_lines(lines, known_codes)


def add_scan(source_id, result, sightings, expired_sightings, reward_suggestions):
    active, expired, rewards = result
    for code in active: sightings[code].add(source_id)
    for code in expired: expired_sightings[code].add(source_id)
    for code, reward in rewards.items(): reward_suggestions[code][reward_key(reward)]["sources"].add(source_id); reward_suggestions[code][reward_key(reward)]["text"] = reward


def scan_dynamic_reddit(known_codes: set[str]):
    """Return (endpoint_successes, scans_by_actual_post_id)."""
    endpoint_successes = 0
    scans_by_post = {}
    for query in REDDIT_SEARCHES:
        url = "https://www.reddit.com/search.json?q=" + quote(query) + "&sort=new&t=week&limit=35&raw_json=1"
        try:
            payload = fetch(url).json(); endpoint_successes += 1
            for child in payload.get("data", {}).get("children", []):
                data = child.get("data", {}) if isinstance(child, dict) else {}
                post_id = str(data.get("id") or "").strip()
                if not post_id: continue
                lines = []
                for key in ("title", "selftext"):
                    value = data.get(key)
                    if isinstance(value, str) and value: lines.extend(value.splitlines())
                result = parse_lines(lines, known_codes)
                key = "reddit-post:" + post_id
                if key in scans_by_post:
                    a,e,r = scans_by_post[key]; na,ne,nr = result
                    a |= na; e |= ne; r.update(nr); scans_by_post[key] = (a,e,r)
                else:
                    scans_by_post[key] = result
        except Exception as exc:
            print(f"Warning: Reddit search failed for {query!r}: {exc}", file=sys.stderr)
    return endpoint_successes, scans_by_post


def best_corroborated_reward(suggestions) -> str | None:
    best = None
    for entry in suggestions.values():
        score = len(entry["sources"])
        if score >= 2 and (best is None or score > best[0] or (score == best[0] and len(entry["text"]) < len(best[1]))):
            best = (score, entry["text"])
    return best[1] if best else None


def main() -> int:
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing = {norm(item["code"]): item for item in current.get("codes", [])}
    known_codes = set(existing)
    sightings: dict[str, set[str]] = defaultdict(set)
    expired_sightings: dict[str, set[str]] = defaultdict(set)
    reward_suggestions = defaultdict(lambda: defaultdict(lambda: {"sources": set(), "text": ""}))

    successful_endpoints = 0
    for source_id, url, kind in STATIC_SOURCES:
        try:
            response = fetch(url); successful_endpoints += 1
            result = scan_reddit_payload(response.json(), known_codes) if kind == "reddit" else scan_html(response.text, known_codes)
            add_scan(source_id, result, sightings, expired_sightings, reward_suggestions)
            print(f"{source_id}: {len(result[0])} active, {len(result[1])} expired candidates")
        except Exception as exc:
            print(f"Warning: {source_id} failed: {exc}", file=sys.stderr)

    dynamic_successes, dynamic_scans = scan_dynamic_reddit(known_codes)
    successful_endpoints += dynamic_successes
    for source_id, result in dynamic_scans.items():
        add_scan(source_id, result, sightings, expired_sightings, reward_suggestions)

    if successful_endpoints < 2:
        print("Safety stop: fewer than two source endpoints were reachable.", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc); today = now.date().isoformat(); changed = False

    # Refresh existing records and promote status when corroboration accumulates.
    for code_key, item in existing.items():
        historical = canonical_historical_sources(item.get("observedSources"))
        before_sources = set(historical)
        historical |= sightings.get(code_key, set()) | expired_sightings.get(code_key, set())
        if historical != before_sources or item.get("observedSources") != sorted(historical):
            item["observedSources"] = sorted(historical); changed = True
        if item.get("sourceCount") != len(historical): item["sourceCount"] = len(historical); changed = True
        if (sightings.get(code_key) or expired_sightings.get(code_key)) and item.get("lastSeen") != today:
            item["lastSeen"] = today; changed = True
        if item.get("status") != "confirmed" and len(historical) >= 2:
            item["status"] = "confirmed"; changed = True

        expired_hist = canonical_historical_sources(item.get("expiredSources")) | expired_sightings.get(code_key, set())
        if item.get("expiredSources") != sorted(expired_hist): item["expiredSources"] = sorted(expired_hist); changed = True
        availability = item.get("availability", "active")
        if len(expired_hist) >= 2 and availability != "expired":
            item["availability"] = "expired"; changed = True
        elif availability == "expired" and len(sightings.get(code_key, set())) >= 2 and not expired_sightings.get(code_key):
            item["availability"] = "active"; item["expiredSources"] = []; changed = True
        elif "availability" not in item:
            item["availability"] = "active"; changed = True

        if not item.get("reward") or item.get("reward") == "Reward not yet identified":
            reward = best_corroborated_reward(reward_suggestions.get(code_key, {}))
            if reward:
                item["reward"] = reward
                if item.get("category", "Unknown") == "Unknown": item["category"] = infer_category(reward)
                changed = True

    # Add new discoveries. One source = Unverified; two independent sources = Confirmed.
    all_discovered = set(sightings) | set(expired_sightings)
    for code_key in sorted(all_discovered):
        if code_key in existing or code_key in STOPWORDS or len(code_key) < 6: continue
        sources = sightings.get(code_key, set()) | expired_sightings.get(code_key, set())
        reward = best_corroborated_reward(reward_suggestions.get(code_key, {})) or "Reward not yet identified"
        item = {
            "id": code_key, "code": code_key, "reward": reward,
            "category": infer_category(reward) if reward != "Reward not yet identified" else "Unknown",
            "status": "confirmed" if len(sources) >= 2 else "unverified",
            "availability": "expired" if len(expired_sightings.get(code_key, set())) >= 2 else "active",
            "firstSeen": today, "lastSeen": today,
            "observedSources": sorted(sources), "sourceCount": len(sources),
            "expiredSources": sorted(expired_sightings.get(code_key, set())),
        }
        current.setdefault("codes", []).append(item); existing[code_key] = item; changed = True
        print(f"Discovered {code_key} ({item['status']}, {item['availability']}; {len(sources)} source(s))")

    current["codes"] = sorted(current.get("codes", []), key=lambda x: (
        x.get("availability") == "expired", x.get("status") == "unverified", x.get("category", ""), x.get("code", "")
    ))
    if not changed:
        print("No code database changes."); return 0

    current["updated"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    current["databaseVersion"] = now.strftime("%Y.%m.%d.%H%M")
    DATA_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {DATA_FILE.name}: {len(current['codes'])} codes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
