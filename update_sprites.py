#!/usr/bin/env python3
"""
Conservative Fortnite.GG Sprite scraper.

Rules:
- Reads released Sprite cards from https://fortnite.gg/sprites
- Skips cards marked Unreleased
- Preserves existing IDs, state compatibility, rarity, and release order
- Adds newly released base Sprites and variants
- Refuses to overwrite sprites.json when the page cannot be parsed safely
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "sprites.json"
SOURCE_URL = "https://fortnite.gg/sprites"
VARIANT_PREFIXES = ("Gold", "Gummy", "Galaxy", "Gem", "Holofoil", "Cube", "Quack")
RARITIES = ("mythic", "legendary", "epic", "rare")


def slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def visible_card(img):
    node = img
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        text = " ".join(node.stripped_strings)
        if (
            re.search(r"\b(mythic|legendary|epic|rare|special)\b", text, re.I)
            and ("Not owned" in text or "Unreleased" in text or "Mastered" in text or "%" in text)
        ):
            return node
    return img.parent


def parse_label(alt: str):
    label = re.sub(r"\s+Sprite$", "", alt.strip(), flags=re.I)
    variant = "Base"
    base = label
    for prefix in VARIANT_PREFIXES:
        if label.lower().startswith(prefix.lower() + " "):
            variant = prefix
            base = label[len(prefix):].strip()
            break
    return base, variant


def scrape():
    response = requests.get(
        SOURCE_URL,
        timeout=40,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SpriteDexBot/1.0; +https://github.com/mrawlz17/SpriteDex)"
        },
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    grouped = defaultdict(dict)
    rarity_by_base = {}

    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if not re.search(r"\bSprite$", alt, re.I):
            continue

        card = visible_card(img)
        card_text = " ".join(card.stripped_strings)
        if "Unreleased" in card_text:
            continue

        base, variant = parse_label(alt)
        if not base:
            continue

        image = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if image.startswith("//"):
            image = "https:" + image
        if image.startswith("/"):
            image = "https://fortnite.gg" + image

        rarity_match = re.search(r"\b(mythic|legendary|epic|rare|special)\b", card_text, re.I)
        rarity = rarity_match.group(1).title() if rarity_match else None
        if variant == "Base" and rarity in {r.title() for r in RARITIES}:
            rarity_by_base[base] = rarity

        grouped[base][variant] = {"name": variant, "image": image}

    return grouped, rarity_by_base


def main():
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing_sprites = current.get("sprites", [])
    existing_by_name = {s["name"].casefold(): s for s in existing_sprites}
    previous_entries = sum(len(s.get("variants", [])) for s in existing_sprites)

    grouped, rarity_by_base = scrape()
    scraped_entries = sum(len(v) for v in grouped.values())

    # Safety gate: never shrink or replace the database from a partial/error page.
    if scraped_entries < max(20, int(previous_entries * 0.80)):
        print(
            f"Safety stop: parsed only {scraped_entries} released entries; "
            f"current database has {previous_entries}.",
            file=sys.stderr,
        )
        return 2

    changed = False
    next_order = max((s.get("releaseOrder", 0) for s in existing_sprites), default=0) + 1

    for base_name, scraped_variants in grouped.items():
        sprite = existing_by_name.get(base_name.casefold())
        if sprite is None:
            base_variant = scraped_variants.get("Base")
            if not base_variant:
                continue
            sprite_id = slug(base_name)
            sprite = {
                "id": sprite_id,
                "name": base_name,
                "rarity": rarity_by_base.get(base_name, "Rare"),
                "icon": "✨",
                "releaseOrder": next_order,
                "variants": [],
                "image": base_variant.get("image", ""),
                "source": "Fortnite.GG",
            }
            next_order += 1
            existing_sprites.append(sprite)
            existing_by_name[base_name.casefold()] = sprite
            changed = True

        existing_variants = {v["name"].casefold(): v for v in sprite.get("variants", [])}
        for variant_name, scraped_variant in scraped_variants.items():
            if variant_name.casefold() in existing_variants:
                continue
            variant_id = f"{sprite['id']}-{slug(variant_name)}"
            sprite.setdefault("variants", []).append(
                {
                    "id": variant_id,
                    "name": variant_name,
                    "rareHunt": variant_name not in {"Base", "Gold", "Gummy"},
                }
            )
            changed = True

        if not sprite.get("image") and scraped_variants.get("Base", {}).get("image"):
            sprite["image"] = scraped_variants["Base"]["image"]
            changed = True

    new_entries = sum(len(s.get("variants", [])) for s in existing_sprites)
    if not changed:
        print(f"No changes. {new_entries} released entries.")
        return 0

    now = datetime.now(timezone.utc)
    current["sprites"] = existing_sprites
    current["releasedEntries"] = new_entries
    current["updated"] = now.date().isoformat()
    current["databaseVersion"] = now.strftime("%Y.%m.%d.%H%M")
    current.setdefault("dataChangelog", []).insert(
        0,
        {
            "databaseVersion": current["databaseVersion"],
            "date": now.date().isoformat(),
            "addedEntries": new_entries - previous_entries,
            "source": "Fortnite.GG automatic check",
        },
    )
    current["dataChangelog"] = current["dataChangelog"][:20]

    DATA_FILE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"Updated Sprite database: {previous_entries} -> {new_entries} released entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
