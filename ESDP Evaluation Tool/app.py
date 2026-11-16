"""Loopback-only, single-user ESDP review prototype."""
import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from esdp_review import ROOT, RUBRIC, MAX_BYTES, evaluate, extract


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.busy = threading.BoundedSemaphore(1)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind + ('; charset=utf-8' if kind.startswith('text/') or kind == 'application/json' else ''))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        port = self.server.server_address[1]
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Only local access is supported.'})
        path = urlsplit(self.path).path
        if path == '/api/config':
            return self.send(200, {'token': self.server.token, 'rubric': RUBRIC,
                                   'ai_available': bool(os.environ.get('OPENAI_API_KEY') and os.environ.get('ESDP_MODEL')),
                                   'model': os.environ.get('ESDP_MODEL') or ''})
        files = {'/': ('index.html', 'text/html'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
        if path not in files:
            return self.send(404, {'error': 'Not found.'})
        filename, kind = files[path]
        self.send(200, (ROOT / 'web' / filename).read_bytes(), kind)

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-ESDP-Token') != self.server.token:
            return self.send(403, {'error': 'Refresh this local page before submitting.'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers['Host']:
            return self.send(403, {'error': 'Cross-origin requests are not allowed.'})
        if self.path != '/api/review':
            return self.send(404, {'error': 'Not found.'})
        if not self.server.busy.acquire(blocking=False):
            return self.send(409, {'error': 'A review is running. Wait for it to finish.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BYTES * 4 // 3 + 10000:
                raise ValueError('Upload is empty or exceeds 20 MB.')
            body = json.loads(self.rfile.read(length))
            if body.get('use_ai') not in (True, False) or not isinstance(body.get('filename'), str):
                raise ValueError('Invalid review request.')
            if body['use_ai'] and body.get('consent') is not True:
                raise ValueError('Confirm sending extracted text to OpenAI for AI review.')
            data = base64.b64decode(body.get('data', ''), validate=True)
            doc = extract(body['filename'], data)
            self.send(200, evaluate(doc, body['use_ai']))
        except (ValueError, TypeError, binascii.Error) as exc:
            self.send(400, {'error': str(exc)[:500]})
        except Exception:
            self.send(500, {'error': 'The document could not be processed. Try a valid, unencrypted PDF or DOCX. No review was accepted.'})
        finally:
            self.server.busy.release()

    def log_message(self, fmt, *args):
        # Never log submission text, file names, tokens, API responses or keys.
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    with Server(('127.0.0.1', args.port)) as server:
        print(f'ESDP Review is ready at http://127.0.0.1:{args.port} (keep this window open)', flush=True)
        server.serve_forever()
