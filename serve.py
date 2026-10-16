#!/usr/bin/env python3
"""Serve ./docs locally with the CORS header Stremio needs, for testing on this Mac.

  python3 serve.py            -> http://127.0.0.1:7070/
  python3 serve.py --port 8080   (7000 is used by macOS AirPlay)

Addon URLs to paste into Stremio (Addons > + Add addon) while this runs:
  http://127.0.0.1:7070/marvel/manifest.json
  http://127.0.0.1:7070/dc/manifest.json
A 127.0.0.1 address only works on this computer. Publish the docs folder (see README) for your
TV, phone and other devices.
"""
import argparse
import functools
import http.server
import os

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs')


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{'.json': 'application/json; charset=utf-8'})

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=7070)
    args = ap.parse_args()
    if not os.path.isfile(os.path.join(SITE, 'marvel', 'manifest.json')):
        raise SystemExit('docs/ is missing: run "python3 build.py" first.')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port),
                                             functools.partial(Handler, directory=SITE))
    base = 'http://127.0.0.1:%d' % args.port
    print('Serving %s at %s/  (Ctrl+C to stop)' % (os.path.relpath(SITE), base))
    print('  Marvel: %s/marvel/manifest.json' % base)
    print('  DC:     %s/dc/manifest.json' % base)
    print('When done testing, uninstall these 127.0.0.1 copies in Stremio: addons sync to your')
    print('account, and your TV/phone cannot reach this computer\'s 127.0.0.1.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
