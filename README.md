# SpriteDex

Fortnite Sprite collection tracker with automatic Sprite and Override-code data updates.

## Automatic data updates
- `scripts/update_sprites.py` checks Fortnite.GG daily.
- `scripts/update_codes.py` checks public Override-code sources hourly.
- Each updater writes only its own JSON database.
- Both workflows share one GitHub Actions concurrency group so they cannot push at the same time.

## Data safety
Collection data stays on the device in localStorage with an IndexedDB mirror. Exported `SpriteDex-*.json` files are personal backups and should **not** be committed to this public repository.

## Current app version
**32.0**
