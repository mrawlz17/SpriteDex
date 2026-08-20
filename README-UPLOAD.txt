SpriteDex V30 — Season Archives + Chapter 7 Season 4

UPLOAD / REPLACE THESE FILES IN YOUR GITHUB REPOSITORY:

Repository root:
- index.html
- sprites.json
- manifest.webmanifest
- sw.js
- icon-192.png
- icon-512.png

Folders:
- scripts/update_sprites.py
- .github/workflows/update-sprites.yml

DO NOT upload your SpriteDex-Mike-*.json backup file to GitHub.
That file contains your personal saved collection and is only for restoring your app data.

V30 changes:
- Added a global season selector.
- Chapter 7 Season 4 is the default/current collection.
- Chapter 7 Season 3 is preserved as an archived collection.
- Added an All Seasons history view.
- Home, Collection, Missing, and Family progress now follow the selected season.
- Old Season 3 missing entries no longer count against the current Season 4 hunt.
- Added 12 Chapter 7 Season 4 launch Sprites:
  Jackrabbit, Shadow, Bush, Tails, Killswitch, Adventure, Klombo, Jonesy,
  Sonic, Crown, 8-Bit, and Storm Scout.
- Added Base, Gold, and Cheat Master variants for all 12 Season 4 Sprites.
- Total Sprite entries: 153 (117 archived Season 3 + 36 Season 4).
- Renamed Peely to Peeky Peely to match the current Fortnite.GG listing while
  keeping all existing saved IDs intact.
- Updated the automatic scraper to understand Cheat Master variants.
- New base Sprites found by the automatic scraper are assigned to currentSeason.
- Added the missing GitHub Actions workflow so the daily automatic database check can run.

DATA SAFETY:
- Existing variant IDs were not changed.
- Your current collection ownership/mastery remains compatible.
- Your V29 backup can still be imported into V30.

AUTOMATIC UPDATES:
1. GitHub Actions runs daily.
2. scripts/update_sprites.py checks Fortnite.GG.
3. Only released entries are added.
4. The scraper refuses to replace sprites.json if parsing looks incomplete.
5. SpriteDex downloads the newest sprites.json when it opens.

IMPORTANT FOR A FUTURE NEW SEASON:
When Chapter 7 Season 5 begins, update currentSeason and the seasons list in
sprites.json once. After that, the daily scraper will assign newly discovered
base Sprites to that new current season.
