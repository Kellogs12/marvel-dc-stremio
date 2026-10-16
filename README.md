# Marvel & DC catalogs for Stremio (self-hosted)

Replacements for the community **Marvel** and **DC Universe** Stremio addons, built as plain
static files so they can be hosted for free and never "run out" of server time.

## Why the originals stopped working

| Addon | Installed address | Status (16 Oct 2026) |
|---|---|---|
| Marvel (joaogonp) | `https://addon-marvel.onrender.com/manifest.json` (what Stremio's in-app Community list still installs) | **Suspended** by its owner on Render |
| Marvel, new home | `https://addon-marvel.gonp.deno.net/manifest.json` | Up today, but the author says it keeps exceeding Deno's free tier and going down mid-month |
| DC Universe (tapframe) | `https://addon-dc-cq85.onrender.com/manifest.json` | **Suspended** by its owner, no replacement |
| AIOStreams' own Marketplace "Marvel Universe" / "DC Universe" | Hard-wired to `addon-marvel.gonp.deno.net` and `addon-dc-cq85.onrender.com` (you can't change the address on the configure page; only whoever runs the instance can, via `MARVEL_UNIVERSE_URL` / `DC_UNIVERSE_URL`) | DC shows **no rows at all**; Marvel works only while the Deno server is up |

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

   On a Mac, **Install in Stremio** hands the link to the Stremio desktop app, which has been
   seen to open without installing anything
   ([stremio-bugs#2484](https://github.com/Stremio/stremio-bugs/issues/2484)). If nothing
   appears, use **Install via Stremio Web** or the **+ Add addon** paste method instead.
3. Addons sync with your Stremio account, so they appear on your TV and phone too.

The catalogs show up as rows on the Board and under **Discover → Marvel / DC**. Titles open
normally; your other installed addons provide the streams.

## Using with AIOStreams

If your addons go through an [AIOStreams](https://github.com/Viren070/AIOStreams) instance, add
these as **Custom** addons there instead of installing them in Stremio directly. Don't use
AIOStreams' own Marketplace **Marvel Universe** / **DC Universe** addons: DC's points at the
suspended Render server, and Marvel's at the Deno server that keeps going down mid-month.

1. Open your instance's configure page and sign in to your **existing** setup: choose **I
   already have a configuration** (or **Sign In** in the sidebar) and enter your UUID and password. The other
   two starting options ("Use a ready-made setup", "Set it up myself") create a brand-new setup
   instead.
2. **Addons → Installed**: switch off (or delete) **Marvel Universe** and **DC Universe**.
3. **Addons → Marketplace**: search for **Custom** → **Configure**, set a name and paste the
   manifest URL → **Install**. Do this twice:
   - `DC Universe`: `https://kellogs12.github.io/marvel-dc-stremio/dc/manifest.json`
   - `Marvel`: `https://kellogs12.github.io/marvel-dc-stremio/marvel/manifest.json`
4. **Addons → Installed → Catalogs**: the new catalogs are tagged *New*. Make sure they're
   switched on, and drag them into the order you like.
5. **Save & Install**: the card must say **Save Configuration** with *your* UUID (if it says
   **Create Configuration**, you're not signed in). Click **Save** and wait for "Configuration
   updated successfully".
6. Reinstall AIOStreams in Stremio so it picks up the new rows: under **Direct Manifest URL**
   (or **Manifest URL (alias)**) click the copy icon next to the link. Then in Stremio Web go to
   **Addons**, uninstall the older AIOStreams entry, click **+ Add addon**, paste, **Add**,
   **Install**. (Avoid **Install to Stremio** on a Mac, for the reason above.)

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

## Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| DC (or Marvel) rows missing, but the addon page works | AIOStreams is still using its own Marketplace Marvel Universe / DC Universe | Follow [Using with AIOStreams](#using-with-aiostreams) |
| AIOStreams changes don't stick after saving | Saved while signed out (a new setup was created), or the save was rejected | Sign in with **I already have a configuration**; confirm the card says **Save Configuration** and you get "Configuration updated successfully" |
| AIOStreams error "*X* has been removed: …" (or "*X* has been disabled: …") | An addon in your setup is no longer allowed on your instance (in v2.35.9 that includes TorBox, TorBox Search, USA TV and Debridio TV). AIOStreams rejects the whole setup, even if that addon is switched off | Delete that addon (switching it off isn't enough), then save |
| AIOStreams error "Failed to fetch manifest for *X*" | That addon's server is down or gone, and AIOStreams won't save while it's on | Switch that addon off (you can turn it back on later), then save |
| AIOStreams says "Reinstall required" (or "Reinstall recommended") | Rows were added, removed or reordered, so Stremio's saved copy is out of date | Reinstall AIOStreams in Stremio (step 6 above) |
| No addons listed at all in Stremio | The addon (or AIOStreams) isn't installed in your Stremio account | Install it again with **+ Add addon**; addons sync to all your devices |
| `127.0.0.1` addon works on the Mac only | Local test address | Use the published GitHub Pages address everywhere else |

## Credits

Catalog data and artwork come from [joaogonp/addon-marvel](https://github.com/joaogonp/addon-marvel)
and [tapframe/addon-dc](https://github.com/tapframe/addon-dc) (MIT licence). Watch orders follow
Marvel.com's official Disney+ timeline, and for the DCU, James Gunn's statements. Title details
come from Stremio's Cinemeta at build time. Marvel and DC names and logos are trademarks of their
owners; this is a personal, non-commercial catalog.
