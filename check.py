#!/usr/bin/env python3
"""Sanity-check the built addons before (and after) you publish them.

  python3 check.py                      check docs/ files + every title against the Cinemeta cache
  python3 check.py --posters            also check that every poster image loads
  python3 check.py --streams            also check that every live TV stream answers (run it in Australia)
  python3 check.py --url https://YOU.github.io/stremio-heroes
                                        check the published copy: HTTP 200, CORS header, same data
Exit code is 1 if any error was found (warnings don't fail).
"""
import argparse
import concurrent.futures
import difflib
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, 'docs')
CACHE_FILE = os.path.join(ROOT, 'cache', 'cinemeta.json')
BRANDS = ('marvel', 'dc')
_N = r'(?:0|[1-9]\d*)'
_PRE = r'(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)'
SEMVER = re.compile(r'^%s\.%s\.%s(?:-%s(?:\.%s)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$'
                    % (_N, _N, _N, _PRE, _PRE))

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def exact_case_exists(path):
    """macOS disks ignore case but web hosts don't, so compare each path part literally."""
    rel = os.path.relpath(path, SITE).split(os.sep)
    cur = SITE
    for part in rel:
        if not os.path.isdir(cur) or part not in os.listdir(cur):
            return False
        cur = os.path.join(cur, part)
    return True


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def check_local():
    cache = json.load(open(CACHE_FILE, encoding='utf-8')) if os.path.exists(CACHE_FILE) else {}
    data = {}
    for brand in BRANDS:
        mpath = os.path.join(SITE, brand, 'manifest.json')
        if not os.path.exists(mpath):
            err('%s: manifest.json missing (run build.py)' % brand)
            continue
        m = json.load(open(mpath, encoding='utf-8'))
        for field in ('id', 'version', 'name', 'description', 'resources', 'types', 'catalogs'):
            if not m.get(field):
                err('%s: manifest field "%s" missing' % (brand, field))
        if not SEMVER.match(m.get('version', '')):
            err('%s: version "%s" is not semver' % (brand, m.get('version')))
        if m.get('resources') != ['catalog']:
            err('%s: resources should be ["catalog"]' % brand)
        for key in ('logo', 'background'):
            if not str(m.get(key, '')).startswith('https://'):
                warn('%s: %s is not an https URL' % (brand, key))
        seen = set()
        data[brand] = {'manifest': m, 'catalogs': {}}
        for cat in m.get('catalogs', []):
            key = (cat.get('type'), cat.get('id'))
            if key in seen:
                err('%s: duplicate catalog %s' % (brand, key))
            seen.add(key)
            if any(e.get('isRequired') for e in cat.get('extra', [])):
                err('%s/%s: a required extra hides the catalog from the Board' % (brand, cat['id']))
            if re.search(r'[^A-Za-z0-9_.-]', cat['type'] + cat['id']):
                err('%s/%s: type/id must not need URL-escaping' % (brand, cat['id']))
            path = os.path.join(SITE, brand, 'catalog', cat['type'], cat['id'] + '.json')
            if not exact_case_exists(path):
                err('%s: %s missing (exact case)' % (brand, os.path.relpath(path, SITE)))
                continue
            metas = json.load(open(path, encoding='utf-8')).get('metas')
            data[brand]['catalogs'][cat['id']] = metas
            label = '%s/%s' % (brand, cat['id'])
            if not metas:
                err('%s: empty catalog' % label)
                continue
            ids = set()
            for i, mt in enumerate(metas):
                where = '%s[%d] %s "%s"' % (label, i, mt.get('id'), mt.get('name'))
                if not re.match(r'^tt\d+$', str(mt.get('id'))):
                    err('%s: id is not an IMDb tt id (detail page cannot open)' % where)
                if mt.get('type') not in ('movie', 'series'):
                    err('%s: type must be movie or series' % where)
                if not mt.get('name'):
                    err('%s: no name' % where)
                if not str(mt.get('poster', '')).startswith('https://'):
                    err('%s: poster missing or not https' % where)
                if mt.get('id') in ids:
                    err('%s: duplicate in catalog' % where)
                ids.add(mt.get('id'))
                cm = cache.get('%s/%s' % (mt.get('type'), mt.get('id')))
                if cm is None:
                    warn('%s: not in Cinemeta cache (run build.py --cinemeta)' % where)
                elif cm.get('missing'):
                    other = 'series' if mt.get('type') == 'movie' else 'movie'
                    hint = ''
                    if (cache.get('%s/%s' % (other, mt.get('id'))) or {}).get('name'):
                        hint = ' (Cinemeta has it as %s)' % other
                    err('%s: Cinemeta has no %s with this id%s' % (where, mt.get('type'), hint))
                else:
                    a, b = norm(mt.get('name')), norm(cm.get('name'))
                    if a and b and a not in b and b not in a and difflib.SequenceMatcher(None, a, b).ratio() < 0.6:
                        warn('%s: Cinemeta calls this "%s"' % (where, cm.get('name')))
                    y1 = re.match(r'\d{4}', mt.get('releaseInfo') or '')
                    y2 = re.match(r'\d{4}', str(cm.get('releaseInfo') or cm.get('year') or ''))
                    if y1 and y2 and abs(int(y1.group()) - int(y2.group())) > 1:
                        warn('%s: year %s but Cinemeta says %s' % (where, y1.group(), y2.group()))
    check_tv(data)
    return data


def check_tv(data):
    """The live TV addon serves its own meta and stream files for every channel."""
    mpath = os.path.join(SITE, 'tv', 'manifest.json')
    if not os.path.exists(mpath):
        err('tv: manifest.json missing (run build.py)')
        return
    m = json.load(open(mpath, encoding='utf-8'))
    if not SEMVER.match(m.get('version', '')):
        err('tv: version "%s" is not semver' % m.get('version'))
    res = {r['name'] if isinstance(r, dict) else r: r for r in m.get('resources', [])}
    prefixes = []
    for name in ('meta', 'stream'):
        r = res.get(name)
        if not isinstance(r, dict) or r.get('types') != ['tv'] or not r.get('idPrefixes'):
            err('tv: manifest needs a "%s" resource for type tv with idPrefixes' % name)
        else:
            prefixes = r['idPrefixes']
    data['tv'] = {'manifest': m, 'catalogs': {}}
    seen = set()
    for cat in m.get('catalogs', []):
        path = os.path.join(SITE, 'tv', 'catalog', cat['type'], cat['id'] + '.json')
        if cat['type'] != 'tv' or not exact_case_exists(path):
            err('tv: catalog %s missing or not type tv' % cat['id'])
            continue
        metas = json.load(open(path, encoding='utf-8')).get('metas') or []
        data['tv']['catalogs'][cat['id']] = metas
        if not metas:
            err('tv/%s: empty catalog' % cat['id'])
        for mt in metas:
            where = 'tv/%s %s "%s"' % (cat['id'], mt.get('id'), mt.get('name'))
            cid = str(mt.get('id'))
            if not re.match(r'^[a-z0-9-]+$', cid) or not any(cid.startswith(p) for p in prefixes):
                err('%s: id must be lowercase [a-z0-9-] and start with %s' % (where, prefixes))
            if cid in seen:
                err('%s: id used twice' % where)
            seen.add(cid)
            if mt.get('type') != 'tv' or not mt.get('name'):
                err('%s: needs type tv and a name' % where)
            if not str(mt.get('poster', '')).startswith('https://'):
                err('%s: poster missing or not https' % where)
            for kind in ('meta', 'stream'):
                if not exact_case_exists(os.path.join(SITE, 'tv', kind, 'tv', cid + '.json')):
                    err('%s: %s/tv/%s.json missing' % (where, kind, cid))
            spath = os.path.join(SITE, 'tv', 'stream', 'tv', cid + '.json')
            if os.path.exists(spath):
                streams = json.load(open(spath, encoding='utf-8')).get('streams') or []
                if not streams or not all(str(s.get('url', '')).startswith('https://') for s in streams):
                    err('%s: needs at least one https stream (Stremio Web blocks http)' % where)


def check_streams(data):
    """Fetch the first KB of every live TV stream. Streams are geo-locked to Australia."""
    urls = {}
    for metas in data.get('tv', {}).get('catalogs', {}).values():
        for mt in metas:
            spath = os.path.join(SITE, 'tv', 'stream', 'tv', mt['id'] + '.json')
            for s in json.load(open(spath, encoding='utf-8')).get('streams', []):
                urls[s['url']] = '%s "%s"' % (mt['id'], mt['name'])

    def probe(url):
        status, headers, body = http_get(url, max_bytes=2048)
        ctype = {k.lower(): v for k, v in headers.items()}.get('content-type', '')
        ok = status in (200, 206) and (body[:7] == b'#EXTM3U' or 'mpegurl' in ctype or ctype.startswith('video/'))
        return url, ok, status, ctype

    print('Checking %d live TV streams (this needs an Australian connection)...' % len(urls))
    bad = 0
    plex = sorted(u for u in urls if 'plex.tv' in u)  # Plex rate-limits parallel requests (HTTP 429)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(probe, sorted(set(urls) - set(plex))))
    for u in plex:
        results.append(probe(u))
        time.sleep(0.3)
    for url, ok, status, ctype in results:
        if not ok:
            bad += 1
            warn('stream for %s -> %s %s' % (urls[url], describe(status, b''), ctype))
    print('  %d of %d streams answered' % (len(urls) - bad, len(urls)))


def http_get(url, first_byte_only=False, max_bytes=None):
    headers = {'User-Agent': 'stremio-heroes-check/1.0', 'Origin': 'https://web.stremio.com'}
    if first_byte_only:
        headers['Range'] = 'bytes=0-0'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, dict(r.headers), r.read() if max_bytes is None else r.read(max_bytes)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b''
    except Exception as e:
        return None, {}, str(e).encode()


def describe(status, body):
    return 'HTTP %s' % status if status else 'failed: %s' % body.decode(errors='replace')


def check_image(url, label):
    status, headers, body = http_get(url, first_byte_only=True)
    ctype = {k.lower(): v for k, v in headers.items()}.get('content-type', '')
    if status not in (200, 206):
        err('%s %s -> %s' % (label, url, describe(status, body)))
    elif not ctype.startswith('image/'):
        err('%s %s is %s, not an image' % (label, url, ctype or 'of unknown type'))


def check_posters(data):
    urls = {mt['poster']: 'poster' for b in data.values() for metas in b['catalogs'].values() for mt in metas}
    for b in data.values():
        for key in ('logo', 'background'):
            if b['manifest'].get(key):
                urls[b['manifest'][key]] = key
    print('Checking %d images...' % len(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda u: check_image(u, urls[u]), sorted(urls)))
    for url in urls:
        if '/t/p/original/' in url:
            warn('full-size TMDB image (1-2 MB): %s' % url)


def check_remote(base, data):
    base = base.strip().rstrip('/')
    if base.endswith('/manifest.json'):
        base = base.rsplit('/', 2)[0]
    if not base.startswith('https://') and not re.match(r'https?://(127\.0\.0\.1|localhost)(:|/|$)', base):
        err('%s is not HTTPS; Stremio will refuse it on other devices' % base)
    for brand, local in data.items():
        url = '%s/%s/manifest.json' % (base, brand)
        status, headers, body = http_get(url)
        lower = {k.lower(): v for k, v in headers.items()}
        if status != 200:
            err('%s -> %s' % (url, describe(status, body)))
            continue
        if lower.get('access-control-allow-origin') != '*':
            err('%s: missing "Access-Control-Allow-Origin: *" (Stremio desktop/web will fail)' % url)
        try:
            remote = json.loads(body)
        except ValueError:
            err('%s: not JSON' % url)
            continue
        if remote != local['manifest']:
            warn('%s differs from local build (old upload, or host cache - wait ~10 min)' % url)
        for cat in remote.get('catalogs', []):
            curl = '%s/%s/catalog/%s/%s.json' % (base, brand, cat['type'], cat['id'])
            status, headers, body = http_get(curl)
            lower = {k.lower(): v for k, v in headers.items()}
            if status != 200:
                err('%s -> %s' % (curl, describe(status, body)))
                continue
            if lower.get('access-control-allow-origin') != '*':
                err('%s: missing CORS header' % curl)
            try:
                metas = json.loads(body)['metas']
            except (ValueError, KeyError):
                err('%s: not a {"metas": [...]} JSON (wrong path or 404 page?)' % curl)
                continue
            if metas != local['catalogs'].get(cat['id']):
                warn('%s differs from local build' % curl)
        print('  checked %s (%d catalogs)' % (url, len(remote.get('catalogs', []))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--posters', action='store_true', help='check every poster and logo URL loads as an image')
    ap.add_argument('--streams', action='store_true', help='check every live TV stream answers (from Australia)')
    ap.add_argument('--url', help='published base URL (the folder that contains marvel/ and dc/)')
    args = ap.parse_args()
    data = check_local()
    if args.posters:
        check_posters(data)
    if args.streams:
        check_streams(data)
    if args.url:
        check_remote(args.url, data)
    total = sum(len(m) for b in data.values() for m in b['catalogs'].values())
    for w in warnings:
        print('WARN ', w)
    for e in errors:
        print('ERROR', e)
    print('\n%d catalogs, %d entries: %d errors, %d warnings' % (
        sum(len(b['catalogs']) for b in data.values()), total, len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
