# SpriteDex

Fortnite Sprite collection tracker with automatic Sprite database updates.

## Automatic data updates
- `scripts/update_sprites.py` checks Fortnite.GG daily.
- The Sprite updater writes only `sprites.json`.
- Archived season data remains protected by the current-season roster safeguards.

## Data safety
Collection data stays on the device in localStorage with an IndexedDB mirror. Exported `SpriteDex-*.json` files are personal backups and should **not** be committed to this public repository.

## Current app version
**32.1**
