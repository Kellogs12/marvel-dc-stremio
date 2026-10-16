#!/usr/bin/env python3
"""Build two static Stremio catalog addons (Marvel, DC Universe) into ./docs.

The output is plain JSON files, so it can be hosted on any static host that sends
`Access-Control-Allow-Origin: *` (GitHub Pages and Cloudflare Pages do by default).

Inputs:
  upstream/<brand>/*.js      catalog data vendored from the original open-source addons
  curation/<brand>.json      our fixes: corrected ids/titles/types, re-ordered lists, new titles
  cache/cinemeta.json        descriptions / genres / ratings / release dates from Cinemeta

Usage:
  python3 build.py                     build docs/ (offline, uses the cache)
  python3 build.py --cinemeta          also fetch Cinemeta data for titles not in the cache yet
  python3 build.py --tv-refresh        also download fresh live TV channel lists (see livetv.py)
  python3 build.py --base-url URL      the published address of docs/ (used for logo links),
                                       default https://kellogs12.github.io/marvel-dc-stremio
Only the Python 3 standard library is used.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import livetv  # noqa: E402  (lives next to this file)

ROOT = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.path.join(ROOT, 'upstream')
CURATION = os.path.join(ROOT, 'curation')
CACHE_FILE = os.path.join(ROOT, 'cache', 'cinemeta.json')
SITE = os.path.join(ROOT, 'docs')  # GitHub Pages serves this folder

# Bump this whenever the manifests change (catalog list or names, logos), then reinstall the
# addon in Stremio: Stremio keeps the manifest it saw at install time.
VERSION = '1.0.0'
DEFAULT_BASE_URL = 'https://kellogs12.github.io/marvel-dc-stremio'
CINEMETA = 'https://v3-cinemeta.strem.io/meta/{type}/{id}.json'
METAHUB_POSTER = 'https://images.metahub.space/poster/medium/{id}/img'

# Catalog order here is the row order on the Stremio Board.
# 'files'  = upstream data files concatenated in order
# 'from'   = build from other catalogs of this addon (after their fixes/additions)
# 'sort'   = 'year' to stable-sort by release year, then by exact release date
ADDONS = {
    'marvel': {
        'id': 'selfhosted.heroes.marvel',
        'name': 'Marvel',
        'type': 'Marvel',
        'description': 'The Marvel catalog: MCU in chronological and release order, X-Men, '
                       'movies, series and animations. Self-hosted static build.',
        'upstream_logo': 'https://raw.githubusercontent.com/joaogonp/addon-marvel/main/public/assets/icon.png',
        'upstream_background': 'https://raw.githubusercontent.com/joaogonp/addon-marvel/main/public/assets/background.jpg',
        'catalogs': [
            {'id': 'marvel-mcu', 'name': 'MCU Chronological Order', 'files': ['chronologicalData']},
            {'id': 'release-order', 'name': 'MCU Release Order', 'files': ['releaseData']},
            {'id': 'xmen', 'name': 'X-Men', 'files': ['xmenData']},
            {'id': 'movies', 'name': 'Movies', 'files': ['moviesData'], 'sort': 'year'},
            {'id': 'series', 'name': 'Series', 'files': ['seriesData'], 'sort': 'year'},
            {'id': 'animations', 'name': 'Animations', 'files': ['animationsData'], 'sort': 'year'},
        ],
    },
    'dc': {
        'id': 'selfhosted.heroes.dc',
        'name': 'DC Universe',
        'type': 'DC',
        'description': 'The DC catalog: DCEU and DCU in order, movies, series, animations, '
                       'Batman and Superman collections. Self-hosted static build.',
        'upstream_logo': 'https://raw.githubusercontent.com/tapframe/addon-dc/main/assets/icon.png',
        'upstream_background': 'https://raw.githubusercontent.com/tapframe/addon-dc/main/assets/background.jpg',
        'catalogs': [
            {'id': 'dc-chronological', 'name': 'DCEU Chronological Order', 'files': ['chronologicalData']},
            {'id': 'dc-release', 'name': 'Release Order', 'from': ['dc-movies', 'dc-series'], 'sort': 'year'},
            # 'dcu' (DC Studios, 2024+) is defined entirely in curation/dc.json.
            {'id': 'dcu', 'name': 'DCU: Gods and Monsters', 'files': []},
            {'id': 'dc-movies', 'name': 'Movies', 'files': ['moviesData'], 'sort': 'year'},
            {'id': 'dceu_movies', 'name': 'DCEU Movies', 'files': ['DCEUMovies'], 'sort': 'year'},
            {'id': 'dc-series', 'name': 'Series', 'files': ['seriesData'], 'sort': 'year'},
            {'id': 'dc_modern_series', 'name': 'DC Modern Series', 'files': ['DCSeries'], 'sort': 'year'},
            {'id': 'dc-animations', 'name': 'Animations',
             'from': ['dc-animations-base', 'dc-batman-animations', 'dc-superman-animations'], 'sort': 'year'},
            {'id': 'dc-batman-animations', 'name': 'Batman Animations', 'files': ['everythingbatmananimation'],
             'sort': 'year'},
            {'id': 'dc-superman-animations', 'name': 'Superman Animations', 'files': ['everythingsupermananimation'],
             'sort': 'year'},
            {'id': 'dc-batman', 'name': 'Batman Collection', 'files': ['everythingbatman'], 'sort': 'year'},
            {'id': 'dc-superman', 'name': 'Superman Collection', 'files': ['everythingsuperman'], 'sort': 'year'},
            # Not published; feeds the merged 'dc-animations' catalog above.
            {'id': 'dc-animations-base', 'name': None, 'files': ['animationsData'], 'hidden': True},
        ],
    },
}

warnings = []


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------- loading

_JS_PREFIX = re.compile(r'^﻿?\s*(?:export\s+default|module\.exports\s*=)\s*')


def _strip_js(src):
    """Remove // and /* */ comments and trailing commas, leaving string literals alone."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == '\\' else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif c in ']}':
            k = len(out) - 1
            while k >= 0 and out[k].isspace():
                k -= 1
            if k >= 0 and out[k] == ',':
                del out[k]
            out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def load_js_array(path):
    """Parse an upstream `export default [...]` / `module.exports = [...]` data file."""
    with open(path, encoding='utf-8') as f:
        body = _JS_PREFIX.sub('', f.read(), count=1).strip()
    if body.endswith(';'):
        body = body[:-1].rstrip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return json.loads(_strip_js(body))


def clean(s):
    return ' '.join(str(s or '').split())


def normalise(raw):
    t = clean(raw.get('type') or 'movie').lower()
    return {
        'imdbId': clean(raw.get('imdbId') or raw.get('id')),
        'title': clean(raw.get('title')),
        'type': 'series' if t in ('series', 'tv') else 'movie',
        'year': clean(raw.get('releaseYear') or raw.get('year')),
        'poster': raw.get('poster') or None,
    }


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------- curation

def year_key(year):
    m = re.match(r'\s*(\d{4})', year or '')
    return int(m.group(1)) if m else 9999


def apply_item_fixes(items, fixes, used=None):
    """Fixes match the item's ORIGINAL id (+ title when given), so id swaps don't cascade."""
    out = []
    for it in items:
        new = dict(it)
        for n, fx in enumerate(fixes):
            if fx['matchImdbId'] != it['imdbId']:
                continue
            if fx.get('matchTitle') and clean(fx['matchTitle']).lower() != it['title'].lower():
                continue
            if used is not None:
                used.add(n)
            if fx['field'] == 'drop':
                new = None
                break
            new[fx['field']] = clean(fx['to'])
        if new is not None:
            out.append(new)
    return out


def dedupe(items):
    seen, out = set(), []
    for it in items:
        if it['imdbId'] in seen:
            continue
        seen.add(it['imdbId'])
        out.append(it)
    return out


def insert_by_year(items, new):
    """Insert after the last item released in the same year or earlier."""
    k = year_key(new['year'])
    pos = 0
    for i, it in enumerate(items):
        if year_key(it['year']) <= k:
            pos = i + 1
    items.insert(pos, new)


def apply_sequence(items, seq):
    """Make the ids in `seq` appear in that relative order, keeping their slots."""
    seq = list(dict.fromkeys(seq))
    idx = [i for i, it in enumerate(items) if it['imdbId'] in seq]
    found = {items[i]['imdbId']: items[i] for i in idx}
    for i, it in zip(idx, [found[s] for s in seq if s in found]):
        items[i] = it
    return len(idx)


def normalise_curated(x, poster_pool):
    imdb = clean(x['imdbId'])
    return {
        'imdbId': imdb,
        'title': clean(x['title']),
        'type': 'series' if x['type'] in ('series', 'tv') else 'movie',
        'year': clean(x.get('year')),
        'poster': x.get('poster') or poster_pool.get(imdb),
    }


def build_catalog_items(brand, cat, built, cur, poster_pool, sort_key, used):
    if cat.get('from'):
        items = [dict(it) for cid in cat['from'] for it in built[cid]]
    else:
        items = []
        for name in cat.get('files', []):
            items += [normalise(r) for r in load_js_array(os.path.join(UPSTREAM, brand, name + '.js'))]
        items = apply_item_fixes(items, cur.get('itemFixes', []))
    items = dedupe(items)

    ordered = {c['catalogId']: c for c in cur.get('orderedCatalogs', [])}
    if cat['id'] in ordered:
        # Full replacement list (curated watch orders, new catalogs).
        items = [normalise_curated(x, poster_pool) for x in ordered[cat['id']]['items']]
    else:
        for n, r in enumerate(cur.get('removals', [])):
            if r['catalogId'] == cat['id'] and any(it['imdbId'] == r['imdbId'] for it in items):
                used['removals'].add(n)
                items = [it for it in items if it['imdbId'] != r['imdbId']]
        have = {it['imdbId'] for it in items}
        for n, add in enumerate(cur.get('additions', [])):
            if add['catalogId'] == cat['id'] and clean(add['imdbId']) not in have:
                used['additions'].add(n)
                insert_by_year(items, normalise_curated(add, poster_pool))
                have.add(clean(add['imdbId']))
        if cat.get('sort') == 'year':
            items.sort(key=sort_key)
    for n, seq in enumerate(cur.get('sequences', [])):
        if seq['catalogId'] in ('*', cat['id']) and apply_sequence(items, seq['ids']) > 1:
            used['sequences'].add(n)
    for it in items:
        it['poster'] = cur.get('posterFixes', {}).get(it['imdbId'], it['poster'])
    return dedupe(items)


def build_poster_pool(brand, cur, used_fixes):
    """First upstream poster seen for each id, so re-ordered lists keep curated artwork."""
    pool = {}
    folder = os.path.join(UPSTREAM, brand)
    for name in sorted(os.listdir(folder)):
        if name.endswith('.js'):
            items = apply_item_fixes([normalise(r) for r in load_js_array(os.path.join(folder, name))],
                                     cur.get('itemFixes', []), used_fixes)
            for it in items:
                if it['poster'] and it['imdbId'] not in pool:
                    pool[it['imdbId']] = it['poster']
    return pool


def report_unused(brand, cur, used):
    for n, fx in enumerate(cur.get('itemFixes', [])):
        if n not in used['itemFixes']:
            warn('%s itemFixes[%d] %s "%s" matched nothing' % (brand, n, fx['matchImdbId'], fx.get('matchTitle', '')))
    for n, r in enumerate(cur.get('removals', [])):
        if n not in used['removals']:
            warn('%s removals[%d] %s from %s removed nothing' % (brand, n, r['imdbId'], r['catalogId']))
    for n, a in enumerate(cur.get('additions', [])):
        if n not in used['additions']:
            warn('%s additions[%d] %s "%s" not added to %s (already there, unknown catalog, or catalog is an '
                 'orderedCatalog)' % (brand, n, a['imdbId'], a.get('title'), a['catalogId']))
    for n, s in enumerate(cur.get('sequences', [])):
        if n not in used['sequences']:
            warn('%s sequences[%d] found fewer than two of its ids anywhere' % (brand, n))


def plan_addons(cache):
    def released(it):
        r = (cache.get(cm_key(it)) or {}).get('released') or ''
        return r[:10] or '9999-99-99'

    def sort_key(it):
        return year_key(it['year']), released(it)

    plan = {}
    for brand, addon in ADDONS.items():
        cur = load_json(os.path.join(CURATION, brand + '.json'), {})
        used = {'itemFixes': set(), 'removals': set(), 'additions': set(), 'sequences': set()}
        pool = build_poster_pool(brand, cur, used['itemFixes'])
        by_id = {c['id']: c for c in addon['catalogs']}
        built = {}

        def get(cid):
            if cid not in built:
                for dep in by_id[cid].get('from', []):
                    get(dep)
                built[cid] = build_catalog_items(brand, by_id[cid], built, cur, pool, sort_key, used)
            return built[cid]

        for cat in addon['catalogs']:
            get(cat['id'])
        plan[brand] = (built, cur, used)
    return plan


# ---------------------------------------------------------------- cinemeta

CM_FIELDS = ('name', 'releaseInfo', 'year', 'released', 'description', 'genres', 'imdbRating', 'poster')


def cm_key(it):
    return '%s/%s' % (it['type'], it['imdbId'])


def fetch_cinemeta(key):
    typ, imdb = key.split('/', 1)
    url = CINEMETA.format(type=typ, id=imdb)
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'stremio-heroes-build/1.0'})
            with urllib.request.urlopen(req, timeout=25) as r:
                meta = (json.load(r) or {}).get('meta')
            if not meta:
                return key, {'missing': True}, None
            return key, {k: meta[k] for k in CM_FIELDS if meta.get(k)}, None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return key, {'missing': True}, None
            last = e
        except Exception as e:  # network/SSL trouble: leave uncached and say why
            last = e
    return key, None, repr(last)


def refresh_cinemeta(cache, keys):
    # Also retry titles Cinemeta didn't know before and ones without a release date yet
    # (usually upcoming titles), so they fill in once Cinemeta catches up.
    todo = sorted(k for k in keys if not (cache.get(k) or {}).get('released'))
    if not todo:
        return
    print('Fetching %d titles from Cinemeta...' % len(todo))
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for key, val, error in pool.map(fetch_cinemeta, todo):
            if val is None:
                failed.append((key, error))
            elif not (val.get('missing') and cache.get(key) and not cache[key].get('missing')):
                cache[key] = val
    if failed:
        print('Warning: %d Cinemeta requests failed (e.g. %s: %s). Run again when online.' % (
            len(failed), failed[0][0], failed[0][1]))
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=1, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------- output

def to_meta(it, cache):
    cm = cache.get(cm_key(it)) or {}
    meta = {'id': it['imdbId'], 'type': it['type'], 'name': it['title']}
    poster = it['poster'] or cm.get('poster') or METAHUB_POSTER.format(id=it['imdbId'])
    # Full-size TMDB images are 1-2 MB each; 500px is plenty for a poster tile.
    meta['poster'] = poster.replace('image.tmdb.org/t/p/original/', 'image.tmdb.org/t/p/w500/')
    release = it['year'] if year_key(it['year']) != 9999 else (cm.get('releaseInfo') or cm.get('year'))
    if release:
        meta['releaseInfo'] = str(release)
    if cm.get('description'):
        meta['description'] = cm['description']
    if cm.get('genres'):
        meta['genres'] = cm['genres']
    if cm.get('imdbRating'):
        meta['imdbRating'] = str(cm['imdbRating'])
    return meta


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def site_base(url):
    if not url:
        return None
    base = url.strip().rstrip('/')
    if base.endswith('/manifest.json'):
        base = base.rsplit('/', 2)[0]
    if not base.startswith('https://'):
        sys.exit('--base-url must be the https:// address of the published docs folder, '
                 'e.g. https://YOU.github.io/stremio-heroes')
    return base


def build(args):
    base = site_base(args.base_url or DEFAULT_BASE_URL)
    if args.tv_refresh:
        print('Refreshing live TV channel lists...')
        livetv.refresh(warn)
    cache = load_json(CACHE_FILE, {})
    plan = plan_addons(cache)
    if args.cinemeta:
        keys = {cm_key(it) for built, _, _ in plan.values() for items in built.values() for it in items}
        refresh_cinemeta(cache, keys)
        plan = plan_addons(cache)  # re-plan: sorting uses release dates from the cache

    # Write into a temporary folder and only replace docs/ once everything succeeded.
    tmp = SITE + '.tmp'
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    summary = []
    for brand, addon in ADDONS.items():
        built, cur, used = plan[brand]
        report_unused(brand, cur, used)
        catalogs = []
        for cat in addon['catalogs']:
            items = built[cat['id']]
            if cat.get('hidden'):
                continue
            if not items:
                warn('%s / %s is empty and was left out of the manifest' % (addon['name'], cat['name']))
                continue
            catalogs.append({'type': addon['type'], 'id': cat['id'], 'name': cat['name']})
            write_json(os.path.join(tmp, brand, 'catalog', addon['type'], cat['id'] + '.json'),
                       {'metas': [to_meta(it, cache) for it in items]})
            summary.append((addon['name'], cat['name'], len(items)))
        shutil.copytree(os.path.join(UPSTREAM, brand, 'assets'), os.path.join(tmp, brand, 'assets'))
        manifest = {
            'id': addon['id'],
            'version': VERSION,
            'name': addon['name'],
            'description': addon['description'],
            'logo': base + '/%s/assets/icon.png' % brand if base else addon['upstream_logo'],
            'background': base + '/%s/assets/background.jpg' % brand if base else addon['upstream_background'],
            'resources': ['catalog'],
            'types': ['movie', 'series'],
            'catalogs': catalogs,
            'behaviorHints': {'configurable': False, 'configurationRequired': False},
        }
        write_json(os.path.join(tmp, brand, 'manifest.json'), manifest)

    for cname, n in livetv.build(os.path.join(tmp, 'tv'), base, write_json):
        summary.append(('AU Live TV', cname, n))

    for name in ('index.html', '404.html', '_headers'):
        shutil.copy(os.path.join(ROOT, 'web', name), os.path.join(tmp, name))
    open(os.path.join(tmp, '.nojekyll'), 'w').close()
    if os.path.isdir(SITE):
        shutil.rmtree(SITE)
    os.rename(tmp, SITE)

    width = max([len(a) + len(c) for a, c, _ in summary] or [0]) + 3
    for a, c, n in summary:
        print('  %-*s %4d %s' % (width, a + ' / ' + c, n, 'channels' if a == 'AU Live TV' else 'titles'))
    missing = sorted({cm_key(it) for built, _, _ in plan.values() for items in built.values() for it in items
                      if (cache.get(cm_key(it)) or {}).get('missing')})
    if missing:
        warn('%d titles are unknown to Cinemeta, so their detail page will not open: %s'
             % (len(missing), ', '.join(missing)))
    for w in warnings:
        print('Warning:', w)
    print('\nBuilt %s' % os.path.relpath(SITE))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cinemeta', action='store_true', help='fetch Cinemeta data for titles missing from the cache')
    ap.add_argument('--tv-refresh', action='store_true', help='download fresh live TV channel lists first')
    ap.add_argument('--base-url', help='public https URL of the published docs folder, used for logo links '
                                       '(default %s)' % DEFAULT_BASE_URL)
    build(ap.parse_args())


if __name__ == '__main__':
    sys.exit(main())
