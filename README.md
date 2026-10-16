# Marvel & DC catalogs for Stremio (self-hosted)

Replacements for the community **Marvel** and **DC Universe** Stremio addons, built as plain
static files so they can be hosted for free and never "run out" of server time.

## Why the originals stopped working

| Addon | Installed address | Status (16 Oct 2026) |
|---|---|---|
| Marvel (joaogonp) | `https://addon-marvel.onrender.com/manifest.json` (what Stremio's in-app Community list still installs) | **Suspended** by its owner on Render |
| Marvel, new home | `https://addon-marvel.gonp.deno.net/manifest.json` | Up today, but the author says it keeps exceeding Deno's free tier and going down mid-month |
| DC Universe (tapframe) | `https://addon-dc-cq85.onrender.com/manifest.json` | **Suspended** by its owner, no replacement |

Both are *catalog-only* addons: they just list IMDb ids in a particular order. Stremio's built-in
Cinemeta addon supplies the details and your other addons supply streams, so a static copy works
exactly like the original.

## What's in it

**Marvel**: MCU Chronological Order (Marvel's official Disney+ timeline, incl. One-Shots, I Am
Groot, Eyes of Wakanda, Marvel Zombies, Spider-Man: Brand New Day, VisionQuest), MCU Release
Order, X-Men, Movies, Series, Animations.

**DC Universe**: DCEU Chronological Order, Release Order, **DCU: Gods and Monsters** (new: Clayface,
Creature Commandos, Superman, Peacemaker, Supergirl, Lanterns, Man of Tomorrow), Movies, DCEU
Movies, Series, DC Modern Series, Animations, Batman Animations, Superman Animations, Batman
Collection, Superman Collection.

Compared with the originals: broken entries fixed (wrong/swapped IMDb ids, titles typed as the
wrong kind so they wouldn't open, typos, duplicates, non-Marvel/DC titles), 87 missing titles
added through October 2026 (565 in total), and descriptions, genres and ratings filled in. Every
title was checked against Cinemeta so its detail page opens.

## Install in Stremio

Published with GitHub Pages at **https://kellogs12.github.io/marvel-dc-stremio/**

1. In Stremio open **Addons**, find the old **Marvel** and **DC Universe** addons and click
   **Uninstall** (they're dead, and would otherwise sit alongside the new ones).
2. Open the address above in a browser and click **Install in Stremio** on each card. Or in
   Stremio click **+ Add addon**, paste a manifest URL, click **Add**, then **Install**:
   - `https://kellogs12.github.io/marvel-dc-stremio/marvel/manifest.json`
   - `https://kellogs12.github.io/marvel-dc-stremio/dc/manifest.json`

   (Stremio 4: paste the URL into the Addons search box instead.)
3. Addons sync with your Stremio account, so they appear on your TV and phone too.

The catalogs show up as rows on the Board and under **Discover → Marvel / DC**. Titles open
normally; your other installed addons provide the streams.

## Files

```
build.py        builds docs/ from upstream/ + curation/ + cache/
serve.py        local test server with the CORS header Stremio needs
check.py        validates docs/ and, with --url, the published copy
upstream/       data files from the original addons (MIT licence, see upstream/*/LICENSE)
curation/       our fixes: corrected ids/titles, watch orders, newer titles, DCU catalog
cache/          Cinemeta descriptions/genres/ratings/dates so builds work offline
web/            install page, 404 page and _headers (copied into docs/ on every build;
                edit them here, not in docs/)
docs/           THE OUTPUT: GitHub Pages serves this folder (Settings → Pages: main, /docs)
```

Everything uses macOS's `python3` command. No Node, no API keys. (The first time, macOS may offer
to install the Command Line Tools; click **Install**.)

## Updating the catalogs

Open Terminal in the project folder (type `cd `, drag the folder onto the window, press Return).
If you no longer have it, get a fresh copy:

```bash
git clone https://github.com/Kellogs12/marvel-dc-stremio.git
```

1. Edit `curation/marvel.json` / `curation/dc.json` (format below).
2. Rebuild and check. `build.py` warns about any fix that matched nothing:

   ```bash
   python3 build.py --cinemeta --base-url https://kellogs12.github.io/marvel-dc-stremio
   ```

   ```bash
   python3 check.py --posters
   ```

3. Publish. GitHub Pages redeploys within a couple of minutes:

   ```bash
   git add -A && git commit -m "Update catalogs" && git push
   ```

   If `git push` asks you to sign in, run `~/.local/bin/gh auth login --web` first.
4. Confirm the live copy:

   ```bash
   python3 check.py --url https://kellogs12.github.io/marvel-dc-stremio
   ```

Catalog *contents* refresh on their own (GitHub caches for about 10 minutes). Stremio keeps the
**manifest** it saw at install time, though. If you add, remove or rename catalogs, or change
the logos, also bump `VERSION` in `build.py` (e.g. `1.0.1`), rebuild and push, then click
**Install** again on the install page (same URL) once. That refreshes the copy in your account.

## Local testing (this Mac only)

```bash
python3 serve.py
```

Then in the Stremio desktop app click **+ Add addon** and paste
`http://127.0.0.1:7070/marvel/manifest.json`. Port 7000 is taken by macOS AirPlay, hence 7070.
Stremio Web (web.stremio.com) blocks `127.0.0.1` addresses, so this only works in the app.

When you're done, **Uninstall** the 127.0.0.1 copies. Addons sync to your account, so otherwise
your TV and phone get rows that can't load (127.0.0.1 means "this device" there), and every row
shows twice on the Mac.

## Hosting somewhere else

Any static host that sends `Access-Control-Allow-Origin: *` over HTTPS works. For Cloudflare
Pages: dash.cloudflare.com → **Workers & Pages** → **Create application** → under *Looking to
deploy Pages?* choose **Get started** → **Drag and drop your files** → name the project, drag the
`docs` folder in → **Deploy site**. Rebuild with `--base-url` set to the new address first.

### Curation format

```jsonc
{
  "itemFixes":  [{"matchImdbId": "tt…", "matchTitle": "as upstream", "field": "title|type|year|imdbId|drop", "to": "…"}],
  "posterFixes": {"tt…": "https://…jpg"},
  "removals":   [{"catalogId": "movies", "imdbId": "tt…", "reason": "…"}],
  "additions":  [{"catalogId": "movies", "imdbId": "tt…", "title": "…", "type": "movie", "year": "2026"}],
  "sequences":  [{"catalogId": "*", "ids": ["tt_part1", "tt_part2", "tt_part3"]}],
  "orderedCatalogs": [{"catalogId": "marvel-mcu", "items": [{"imdbId": "tt…", "title": "…", "type": "movie", "year": "2011"}]}]
}
```

- `orderedCatalogs` replaces a catalog's whole list (the watch orders and the DCU row).
- `additions` slot new titles in by year; year-sorted rows then order by exact release date.
- DC "Release Order" is built from DC Movies + Series, and DC "Animations" merges the Batman and
  Superman animation rows, so add titles to those rows rather than directly.
- `type` must be the one Cinemeta uses (`check.py` tells you if a title won't open).

## Credits

Catalog data and artwork come from [joaogonp/addon-marvel](https://github.com/joaogonp/addon-marvel)
and [tapframe/addon-dc](https://github.com/tapframe/addon-dc) (MIT licence). Watch orders follow
Marvel.com's official Disney+ timeline, and for the DCU, James Gunn's statements. Title details
come from Stremio's Cinemeta at build time. Marvel and DC names and logos are trademarks of their
owners; this is a personal, non-commercial catalog.
