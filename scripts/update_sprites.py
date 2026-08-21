#!/usr/bin/env python3
"""
Conservative Fortnite.GG Sprite scraper for SpriteDex.

Season-safety rules:
- Reads released Sprite cards from https://fortnite.gg/sprites.
- Skips cards marked Unreleased.
- Preserves existing IDs, local-state compatibility, rarity, and release order.
- Adds variants only to records already assigned to the current season.
- A Sprite name that exists only in an archived season is NOT automatically
  copied into the current season.
- Truly new Sprite names that have never appeared in the database may be added
  to the current season.
- Archived season records are frozen.
- Includes a one-time C7S4 repair for the 2026-08-21 updater bug that appended
  archived Sprites to C7S4 after release order 37.
- Refuses to overwrite sprites.json when Fortnite.GG cannot be parsed safely.
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

VARIANT_PREFIXES = (
    "Cheat Master",
    "Holofoil",
    "Galaxy",
    "Gummy",
    "Gold",
    "Gem",
    "Cube",
    "Quack",
)
RARITIES = ("mythic", "legendary", "epic", "rare")

# One-time repair boundary. C7S4 was intentionally seeded with releaseOrder
# 26-37. The buggy 2026-08-21 run appended old-season duplicates starting at 38.
SEASON_REPAIR_CUTOFFS = {
    "C7S4": 37,
}


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
            and (
                "Not owned" in text
                or "Unreleased" in text
                or "Mastered" in text
                or "%" in text
            )
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
            base = label[len(prefix) :].strip()
            break
    return base, variant


def scrape():
    response = requests.get(
        SOURCE_URL,
        timeout=40,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; SpriteDexBot/2.0; "
                "+https://github.com/mrawlz17/SpriteDex)"
            )
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

        image = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or ""
        )
        if image.startswith("//"):
            image = "https:" + image
        if image.startswith("/"):
            image = "https://fortnite.gg" + image

        rarity_match = re.search(
            r"\b(mythic|legendary|epic|rare|special)\b", card_text, re.I
        )
        rarity = rarity_match.group(1).title() if rarity_match else None
        if variant == "Base" and rarity in {r.title() for r in RARITIES}:
            rarity_by_base[base] = rarity

        grouped[base][variant] = {
            "name": variant,
            "image": image,
        }

    return grouped, rarity_by_base


def repair_known_season_pollution(existing_sprites, current_season):
    """
    Remove only records created by the known C7S4 pollution bug.

    A record qualifies only when:
    - it belongs to the current season,
    - its releaseOrder is beyond the clean seeded cutoff, AND
    - the same Sprite name already exists in an archived season.

    This preserves all 12 legitimate C7S4 launch records and preserves future
    genuinely new Sprite names added after releaseOrder 37.
    """
    cutoff = SEASON_REPAIR_CUTOFFS.get(current_season)
    if cutoff is None:
        return existing_sprites, 0, []

    archived_names = {
        s.get("name", "").casefold()
        for s in existing_sprites
        if s.get("season") != current_season
    }

    kept = []
    removed = []
    for sprite in existing_sprites:
        is_pollution = (
            sprite.get("season") == current_season
            and int(sprite.get("releaseOrder", 0) or 0) > cutoff
            and sprite.get("name", "").casefold() in archived_names
        )
        if is_pollution:
            removed.append(sprite)
        else:
            kept.append(sprite)

    removed_entries = sum(len(s.get("variants", [])) for s in removed)
    return kept, removed_entries, [s.get("name", "") for s in removed]


def main():
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing_sprites = current.get("sprites", [])
    current_season = current.get("currentSeason", "")

    current_season_name = next(
        (
            s.get("name")
            for s in current.get("seasons", [])
            if s.get("id") == current_season
        ),
        current_season,
    )

    original_entries = sum(len(s.get("variants", [])) for s in existing_sprites)

    # Repair the known Aug. 21 C7S4 pollution before doing any new discovery.
    existing_sprites, removed_entries, removed_names = repair_known_season_pollution(
        existing_sprites, current_season
    )
    repair_changed = removed_entries > 0

    if repair_changed:
        print(
            f"Season repair: removed {len(removed_names)} archived Sprite duplicates "
            f"({removed_entries} variant entries) from {current_season}."
        )

    # Current-season records are the only records allowed to receive new variants.
    existing_by_name = {
        s["name"].casefold(): s
        for s in existing_sprites
        if s.get("season") == current_season
    }

    # Any name that exists only in an archive must NOT be copied into the current
    # season merely because Fortnite.GG still lists it as released.
    archived_names = {
        s["name"].casefold()
        for s in existing_sprites
        if s.get("season") != current_season
    }

    used_sprite_ids = {s.get("id") for s in existing_sprites}
    baseline_entries = sum(len(s.get("variants", [])) for s in existing_sprites)

    grouped, rarity_by_base = scrape()
    scraped_entries = sum(len(v) for v in grouped.values())

    # Safety gate: a partial/error page must never replace or shrink the database.
    if scraped_entries < max(20, int(baseline_entries * 0.80)):
        print(
            f"Safety stop: parsed only {scraped_entries} released entries; "
            f"clean database has {baseline_entries}.",
            file=sys.stderr,
        )
        return 2

    changed = repair_changed
    next_order = (
        max((s.get("releaseOrder", 0) for s in existing_sprites), default=0) + 1
    )

    skipped_archived = []

    for base_name, scraped_variants in grouped.items():
        key = base_name.casefold()
        sprite = existing_by_name.get(key)

        if sprite is None:
            # Critical season guard: a released Sprite that already belongs to an
            # archived season is not evidence that it belongs to the current one.
            if key in archived_names:
                skipped_archived.append(base_name)
                continue

            # Truly unseen name: safe to add as a new current-season release.
            base_variant = scraped_variants.get("Base")
            if not base_variant:
                continue

            sprite_id = slug(base_name)
            if sprite_id in used_sprite_ids:
                suffix = slug(current_season) or "current"
                sprite_id = f"{sprite_id}-{suffix}"
                serial = 2
                while sprite_id in used_sprite_ids:
                    sprite_id = f"{slug(base_name)}-{suffix}-{serial}"
                    serial += 1

            used_sprite_ids.add(sprite_id)
            sprite = {
                "id": sprite_id,
                "name": base_name,
                "rarity": rarity_by_base.get(base_name, "Rare"),
                "icon": "✨",
                "releaseOrder": next_order,
                "season": current_season,
                "seasonName": current_season_name,
                "variants": [],
                "image": base_variant.get("image", ""),
                "source": "Fortnite.GG",
            }
            next_order += 1
            existing_sprites.append(sprite)
            existing_by_name[key] = sprite
            changed = True
            print(f"New current-season Sprite: {base_name}")

        # Only an already-current-season record reaches this block.
        existing_variants = {
            v["name"].casefold(): v for v in sprite.get("variants", [])
        }

        for variant_name, scraped_variant in scraped_variants.items():
            if variant_name.casefold() in existing_variants:
                continue

            variant_id = f"{sprite['id']}-{slug(variant_name)}"
            sprite.setdefault("variants", []).append(
                {
                    "id": variant_id,
                    "name": variant_name,
                    "rareHunt": variant_name
                    not in {"Base", "Gold", "Gummy"},
                }
            )
            changed = True
            print(f"New variant: {base_name} / {variant_name}")

        if (
            not sprite.get("image")
            and scraped_variants.get("Base", {}).get("image")
        ):
            sprite["image"] = scraped_variants["Base"]["image"]
            changed = True

    new_entries = sum(len(s.get("variants", [])) for s in existing_sprites)

    if not changed:
        print(
            f"No changes. {new_entries} released entries. "
            f"Skipped {len(set(skipped_archived))} archived Sprite names."
        )
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
            "addedEntries": max(0, new_entries - baseline_entries),
            "removedEntries": removed_entries,
            "source": "Fortnite.GG automatic check with season guard",
        },
    )
    current["dataChangelog"] = current["dataChangelog"][:20]

    DATA_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Updated Sprite database: {original_entries} -> {new_entries} released entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
