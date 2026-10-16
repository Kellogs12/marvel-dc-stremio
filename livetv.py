"""AU Live TV: a static Stremio addon built from free, official live streams.

Sources (all point at the broadcasters' / services' own free streams):
  - i.mjh.nz (Matt Huisman): Melbourne free-to-air (ABC, SBS, Seven, Nine, 10, C31)
    and the networks' free online-only channels
  - BuddyChewChew/app-m3u-generator: Plex free live TV, Australian lineup (plex.tv streams)
  - apsattv.com: Samsung TV Plus Australia (Amagi / Wurl / Stingray streams); logos from
    i.mjh.nz's Samsung TV Plus guide

The streams are geo-restricted to Australia by the broadcasters. Used by build.py:
`refresh()` downloads the lists into cache/tv/, `build()` writes <out>/tv/.
"""
import gzip
import io
import json
import os
import re
import shutil
import socket
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'cache', 'tv')
ICON = os.path.join(ROOT, 'web', 'tv-icon.png')

VERSION = '1.0.0'
SOURCES = {
    'mjh': 'https://i.mjh.nz/au/Melbourne/raw-tv.m3u8',
    'plex': 'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plex_au.m3u',
    'samsung': 'https://www.apsattv.com/ssungaus.m3u',
}
SAMSUNG_GUIDE = 'https://i.mjh.nz/SamsungTVPlus/all.xml.gz'
ID_PREFIX = 'autv-'
# Stremio Web only uses its HLS player (hls.js) when a stream reports exactly this type, and most
# broadcasters send 'application/x-mpegURL' instead. Declaring it via proxyHeaders fixes the browser,
# but Stremio's streaming server (desktop, TV and phone apps) then proxies the stream and breaks
# the broadcasters' redirects. So each channel gets a plain stream plus a browser-only one.
HLS_HINT = {'proxyHeaders': {'response': {'content-type': 'application/vnd.apple.mpegurl'}}}
CATALOGS = [
    ('au-fta', 'Melbourne Free-to-Air'),
    ('au-free', 'Free Channels'),
    ('plex', 'Plex Live TV'),
    ('samsung', 'Samsung TV Plus'),
]


# ---------------------------------------------------------------- playlists

def parse_m3u(text):
    """Return [{'name', 'url', <tvg attributes>}] from an extended M3U playlist."""
    out, info = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            head, _, name = line[8:].partition(',')
            info = dict(re.findall(r'([\w-]+)="([^"]*)"', head))
            info['name'] = ' '.join(name.split())
        elif line and not line.startswith('#') and info is not None:
            info['url'] = line
            out.append(info)
            info = None
    return out


def clean_name(name):
    """'Nosey (Australia) alt Geo' -> 'Nosey'; also drops the list's 'find correct' placeholders."""
    name = re.sub(r'\s+(via\s+\S+\s+)?(temp\s+)?find\b.*$', '', name, flags=re.I)
    name = re.sub(r'\s+via\s+\w+\s+source$', '', name, flags=re.I)
    name = re.sub(r'\s+alt$', '', name, flags=re.I)
    name = re.sub(r'\s+(alt\s+)?geo$', '', name, flags=re.I)
    name = re.sub(r'\s*\((australia|au|us|substitute)\)', '', name, flags=re.I)
    return ' '.join(name.split())


def name_key(name):
    return re.sub(r'[^a-z0-9]', '', clean_name(name).lower())


def slug(text):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', text.lower())).strip('-')


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (stremio-heroes live-tv builder)'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _resolves(host):
    """Does the host still exist? Asks Cloudflare DNS-over-HTTPS (local VPN/ISP resolvers sometimes
    answer for dead hosts), falling back to the system resolver."""
    try:
        req = urllib.request.Request('https://cloudflare-dns.com/dns-query?type=A&name=' + host,
                                     headers={'Accept': 'application/dns-json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            answer = json.load(r)
        return answer.get('Status') == 0 and any(a.get('type') == 1 for a in answer.get('Answer', []))
    except Exception:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except socket.gaierror:
            return False


def refresh(warn):
    """Download the playlists into cache/tv/. Keeps the previous copy if a download fails."""
    os.makedirs(CACHE, exist_ok=True)
    for key, url in SOURCES.items():
        try:
            text = _get(url).decode('utf-8', 'replace')
            if len(parse_m3u(text)) < 10:
                raise ValueError('only %d channels' % len(parse_m3u(text)))
        except Exception as e:
            warn('live TV: could not refresh %s (%s); keeping the cached list' % (key, e))
            continue
        if key == 'samsung':
            # This list goes stale: drop channels whose stream host no longer exists.
            hosts = {re.sub(r'^https?://([^/:]+).*', r'\1', c['url']) for c in parse_m3u(text)}
            dead = {h for h in hosts if not _resolves(h)}
            kept = ['#EXTM3U'] + ['#EXTINF:-1,%s\n%s' % (c['name'], c['url']) for c in parse_m3u(text)
                                  if re.sub(r'^https?://([^/:]+).*', r'\1', c['url']) not in dead]
            text = '\n'.join(kept) + '\n'
        with open(os.path.join(CACHE, key + '.m3u'), 'w', encoding='utf-8') as f:
            f.write(text)
    try:
        logos = {}
        for _, el in ET.iterparse(io.BytesIO(gzip.decompress(_get(SAMSUNG_GUIDE, 120))), events=('end',)):
            if el.tag == 'channel':
                icon = el.find('icon')
                if icon is not None and icon.get('src'):
                    for dn in el.findall('display-name'):
                        if dn.text:
                            logos.setdefault(name_key(dn.text), icon.get('src'))
            if el.tag in ('channel', 'programme'):
                el.clear()
        with open(os.path.join(CACHE, 'samsung_logos.json'), 'w', encoding='utf-8') as f:
            json.dump(logos, f, indent=0, sort_keys=True)
    except Exception as e:
        warn('live TV: could not refresh Samsung TV Plus logos (%s)' % e)


def _cached(key):
    """Channels from a cached list, minus ones Stremio Web can't play (http) and test entries."""
    path = os.path.join(CACHE, key + '.m3u')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [c for c in parse_m3u(f.read())
                if c['url'].startswith('https://') and not re.search(r'\btest stream\b', c['name'], re.I)]


# ---------------------------------------------------------------- channels

def channels():
    """{catalog id: [channel]} where channel = {id, name, url, logo, description}."""
    seen = set()

    def make_id(raw):
        cid = ID_PREFIX + slug(raw)
        n, base = 2, cid
        while cid in seen:
            cid, n = '%s-%d' % (base, n), n + 1
        seen.add(cid)
        return cid

    out = {cid: [] for cid, _ in CATALOGS}
    fta = []
    for c in _cached('mjh'):
        number = int(c['tvg-chno']) if c.get('tvg-chno', '').isdigit() else None
        if (number and number >= 300) or re.search(r'\bradio\b|in 90 seconds', c['name'], re.I):
            continue  # SBS radio stations, and ABC's 90-second MP4 loops (not live HLS)
        ch = {'id': make_id(c.get('channel-id') or c['name']), 'name': c['name'], 'url': c['url'],
              'logo': c.get('tvg-logo')}
        if number is not None:
            ch['description'] = 'Channel %d · live free-to-air' % number
            fta.append((number, ch))
        else:
            ch['description'] = 'Free live channel (%s)' % ('international' if c.get('group-title') == 'World'
                                                              else 'Australian networks')
            out['au-free'].append(ch)
    out['au-fta'] = [ch for _, ch in sorted(fta, key=lambda p: p[0])]

    for c in sorted(_cached('plex'), key=lambda c: c['name'].casefold()):
        out['plex'].append({'id': make_id('plex-' + (c.get('channel-id') or c['name'])), 'name': c['name'],
                            'url': c['url'], 'logo': c.get('tvg-logo'),
                            'description': 'Free live channel from Plex'})

    logos_path = os.path.join(CACHE, 'samsung_logos.json')
    logos = json.load(open(logos_path, encoding='utf-8')) if os.path.exists(logos_path) else {}
    names = set()
    for c in sorted(_cached('samsung'), key=lambda c: clean_name(c['name']).casefold()):
        name = clean_name(c['name'])
        if name.casefold() in names:
            continue  # the list repeats some channels ('alt' feeds)
        names.add(name.casefold())
        out['samsung'].append({'id': make_id('ss-' + name), 'name': name, 'url': c['url'],
                               'logo': logos.get(name_key(name)),
                               'description': 'Free live channel from Samsung TV Plus'})
    return out


# ---------------------------------------------------------------- output

def build(out_dir, base, write_json):
    """Write the AU Live TV addon into out_dir. Returns [(catalog name, count)]."""
    icon_url = base + '/tv/assets/icon.png'
    lists = channels()
    catalogs, summary = [], []
    for cid, cname in CATALOGS:
        items = lists[cid]
        if not items:
            continue
        catalogs.append({'type': 'tv', 'id': cid, 'name': cname})
        summary.append((cname, len(items)))
        metas = []
        for ch in items:
            meta = {'id': ch['id'], 'type': 'tv', 'name': ch['name'], 'poster': ch['logo'] or icon_url,
                    'posterShape': 'square', 'logo': ch['logo'] or icon_url,
                    'description': ch['description'], 'genres': [cname]}
            metas.append(meta)
            write_json(os.path.join(out_dir, 'meta', 'tv', ch['id'] + '.json'), {'meta': meta})
            write_json(os.path.join(out_dir, 'stream', 'tv', ch['id'] + '.json'), {'streams': [
                {'url': ch['url'], 'name': 'Live', 'title': ch['name']},
                {'url': ch['url'], 'name': 'Live (browser)',
                 'title': '%s\nFor Stremio Web without the streaming server' % ch['name'],
                 'behaviorHints': HLS_HINT},
            ]})
        write_json(os.path.join(out_dir, 'catalog', 'tv', cid + '.json'),
                   {'metas': [{k: m[k] for k in ('id', 'type', 'name', 'poster', 'posterShape', 'description')}
                              for m in metas]})
    os.makedirs(os.path.join(out_dir, 'assets'), exist_ok=True)
    shutil.copy(ICON, os.path.join(out_dir, 'assets', 'icon.png'))
    write_json(os.path.join(out_dir, 'manifest.json'), {
        'id': 'selfhosted.heroes.autv',
        'version': VERSION,
        'name': 'AU Live TV',
        'description': 'Free Australian live TV: ABC, SBS, Seven, Nine, 10 and C31 (Melbourne), the networks\' '
                       'free channels, Plex and Samsung TV Plus. Official free streams; Australia only.',
        'logo': icon_url,
        'resources': ['catalog',
                      {'name': 'meta', 'types': ['tv'], 'idPrefixes': [ID_PREFIX]},
                      {'name': 'stream', 'types': ['tv'], 'idPrefixes': [ID_PREFIX]}],
        'types': ['tv'],
        'idPrefixes': [ID_PREFIX],
        'catalogs': catalogs,
        'behaviorHints': {'configurable': False, 'configurationRequired': False},
    })
    return summary
