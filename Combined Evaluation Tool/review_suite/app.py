"""One production WSGI app serving all three review tools."""
import base64
import binascii
import importlib
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import threading

from flask import Flask, Response, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import modules
from .assistant import corpus

ROOT = modules.ROOT
WEB = Path(__file__).resolve().parent / 'web'
MAX_REQUEST = 30 * 1024 * 1024
# PDFium's native library is shared across both imported engines.
PDF_LOCK = threading.RLock()


def create_app(config=None, assistant=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=MAX_REQUEST,
        DATA_DIR=os.environ.get('REVIEW_DATA_DIR', str(ROOT / 'suite-data')),
        PUBLIC_ORIGIN=os.environ.get('REVIEW_PUBLIC_ORIGIN', '').rstrip('/'),
        ACCESS_TOKEN=os.environ.get('REVIEW_ACCESS_TOKEN', ''),
        TRUST_PROXY=os.environ.get('REVIEW_TRUST_PROXY') == '1',
        IMPORT_LEGACY=os.environ.get('REVIEW_IMPORT_LEGACY', '1') == '1',
        ASSISTANT_FACTORY=os.environ.get('REVIEW_ASSISTANT_FACTORY', ''),
    )
    if config:
        app.config.update(config)
    if assistant is None and app.config['ASSISTANT_FACTORY']:
        module, factory = app.config['ASSISTANT_FACTORY'].split(':', 1)
        assistant = getattr(importlib.import_module(module), factory)()
        if not callable(getattr(assistant, 'answer', None)):
            raise ValueError('Assistant factory must return an object implementing answer().')
    if app.config['TRUST_PROXY']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    public = app.config['PUBLIC_ORIGIN']
    if public and (not public.startswith('https://') or '/' in public[8:]):
        raise ValueError('REVIEW_PUBLIC_ORIGIN must be an HTTPS origin without a path.')
    if public and len(app.config['ACCESS_TOKEN']) < 24:
        raise ValueError('Set REVIEW_ACCESS_TOKEN to at least 24 characters for hosted access.')
    workspaces = {}
    data = Path(app.config['DATA_DIR']).resolve()
    for name, module in [('pdr', modules.pdr), ('cdr', modules.cdr)]:
        target = data / name
        legacy = module.ROOT / 'workspace-data'
        if app.config['IMPORT_LEGACY'] and not target.exists() and legacy.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(legacy, target)
        workspaces[name] = module.Workspace(target, seed=False)
    app.extensions['workspaces'] = workspaces
    app.extensions['assistant'] = assistant
    csrf = secrets.token_urlsafe(32)
    busy = threading.BoundedSemaphore(1)
    cookie_name = 'review_access'

    def authenticated():
        expected = app.config['ACCESS_TOKEN']
        supplied = request.cookies.get(cookie_name, '')
        return bool(expected and secrets.compare_digest(supplied, expected))

    @app.before_request
    def protect():
        if request.path == '/healthz':
            return None
        if public:
            if request.host_url.rstrip('/') != public:
                abort(403, 'Unexpected application origin.')
            if request.path not in {'/login', '/suite/suite.css'} and not authenticated():
                if '/api/' in request.path:
                    abort(401, 'Sign in to the review suite.')
                return send_file(WEB / 'login.html')
        elif request.host.split(':')[0] not in {'localhost', '127.0.0.1', '[::1]'}:
            abort(403, 'Configure REVIEW_PUBLIC_ORIGIN and REVIEW_ACCESS_TOKEN for hosted access.')
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                abort(403, 'Cross-origin requests are not allowed.')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                abort(403, 'Cross-site requests are not allowed.')
            if request.path == '/login':
                return None
            token = request.headers.get('X-Review-Token')
            if request.view_args and request.view_args.get('tool') in workspaces:
                tool = request.view_args['tool']
                token = request.headers.get(f'X-{tool.upper()}-Token')
                expected = workspaces[tool].token
            elif request.path.startswith('/tools/esdp/'):
                token, expected = request.headers.get('X-ESDP-Token'), csrf
            else:
                expected = csrf
            if not token or not secrets.compare_digest(token, expected):
                abort(403, 'Refresh the application before changing data.')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # Legacy rubric UIs use inline style attributes, but no inline scripts.
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-src 'self'; "
            "frame-ancestors 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        if isinstance(exc, (ValueError, TypeError, KeyError, binascii.Error)):
            return jsonify(error='Invalid request: ' + str(exc)[:300]), 400
        # Do not log document contents, API responses, tokens or file names.
        logging.getLogger(__name__).error('Review operation failed (%s)', type(exc).__name__)
        return jsonify(error='The operation could not be completed. Check the input and try again.'), 500

    @app.get('/healthz')
    def health():
        return jsonify(status='ok', service='review-suite')

    @app.post('/login')
    def login():
        if not public:
            abort(404)
        if not secrets.compare_digest(request.form.get('token', ''), app.config['ACCESS_TOKEN']):
            return Response('Access code was not accepted.', status=401)
        response = app.redirect('/')
        response.set_cookie(cookie_name, app.config['ACCESS_TOKEN'], secure=True,
                            httponly=True, samesite='Strict', max_age=8 * 3600)
        return response

    @app.post('/api/logout')
    def logout():
        response = jsonify(ok=True)
        response.delete_cookie(cookie_name, secure=True, httponly=True, samesite='Strict')
        return response

    @app.get('/')
    def index():
        return send_file(WEB / 'index.html')

    @app.get('/suite/<name>')
    def shell_asset(name):
        if name not in {'suite.css', 'suite.js'}:
            abort(404)
        return send_file(WEB / name)

    @app.get('/api/config')
    def config_route():
        return jsonify(csrf_token=csrf, assistant_available=assistant is not None,
                       hosted=bool(public), tools=['pdr', 'cdr', 'esdp'])

    @app.get('/tools/<tool>/')
    @app.get('/tools/<tool>/<asset>')
    def tool_asset(tool, asset='index.html'):
        if tool not in {'pdr', 'cdr', 'esdp'} or asset not in {'index.html', 'style.css', 'app.js'}:
            abort(404)
        module = getattr(modules, tool)
        text = (module.ROOT / 'web' / asset).read_text(encoding='utf-8')
        # Mount the original interfaces under a namespace; standalone tools stay intact.
        if asset in {'index.html', 'app.js'}:
            text = re.sub(r'/(api/|files/|reference/|style\.css|app\.js)',
                          lambda m: f'/tools/{tool}/' + m[1], text)
            text = text.replace('Local workspace', 'Review workspace').replace(
                'Files stay on this computer.', 'Files stay on the application server.')
            text = text.replace('on this computer', 'on the server')
            if tool == 'esdp':
                text = text.replace('href="/"', 'href="/tools/esdp/"')
        kind = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[asset]
        return Response(text, content_type=kind + '; charset=utf-8')

    @app.get('/tools/<tool>/api/workspace')
    @app.get('/tools/<tool>/api/export')
    def snapshot(tool):
        if tool not in workspaces:
            abort(404)
        result = workspaces[tool].snapshot()
        if request.path.endswith('/export'):
            result.pop('csrf_token', None)
        return jsonify(result)

    @app.post('/tools/<tool>/api/<action>')
    def change(tool, action):
        if tool not in workspaces:
            abort(404)
        workspace = workspaces[tool]
        body = request.get_json()
        if not isinstance(body, dict):
            abort(400, 'Expected a JSON object.')
        if action == 'upload':
            if not isinstance(body.get('filename'), str) or type(body.get('use_ai', False)) is not bool:
                abort(400, 'Invalid upload options.')
            if body.get('use_ai') and not workspace.ai_ready:
                abort(400, 'AI reading is not configured.')
            with PDF_LOCK:
                result = workspace.ingest(body['filename'], base64.b64decode(body['data'], validate=True),
                                          body.get('team'), body.get('use_ai', False))
            return jsonify(result)
        if action == 'page':
            workspace.mutate_page(body)
        elif action == 'assessment' and tool == 'cdr':
            workspace.assess(body)
        else:
            abort(404)
        return jsonify(message='Saved; team workspace updated.')

    @app.get('/tools/<tool>/files/<document>/<filename>')
    def source(tool, document, filename):
        if tool not in workspaces or not re.fullmatch('[a-f0-9]{64}', document):
            abort(404)
        if not re.fullmatch(r'document\.pdf|page-\d+\.png', filename):
            abort(404)
        path = workspaces[tool].folder / 'files' / document / filename
        if not path.is_file():
            abort(404)
        return send_file(path)

    @app.get('/tools/<tool>/reference/<filename>')
    def reference(tool, filename):
        paths = {
            ('pdr', 'pilot.pdf'): workspaces['pdr'].folder / 'reference' / 'pilot.pdf',
            ('cdr', 'rubric.docx'): modules.cdr.ROOT / 'CDR_gradingRubric.docx',
            ('cdr', 'assignment.pdf'): modules.cdr.ROOT / 'FinalProjectCDR_AssignmentDescription.docx.pdf',
        }
        path = paths.get((tool, filename))
        if path is None or not path.is_file():
            abort(404)
        return send_file(path)

    @app.get('/tools/esdp/api/config')
    def esdp_config():
        return jsonify(token=csrf, rubric=modules.esdp.RUBRIC,
                       ai_available=bool(os.environ.get('OPENAI_API_KEY') and os.environ.get('ESDP_MODEL')),
                       model=os.environ.get('ESDP_MODEL', ''))

    @app.post('/tools/esdp/api/review')
    def esdp_review():
        body = request.get_json()
        if not isinstance(body, dict) or type(body.get('use_ai')) is not bool or not isinstance(body.get('filename'), str):
            abort(400, 'Invalid review request.')
        if body['use_ai'] and body.get('consent') is not True:
            abort(400, 'Confirm sending extracted text for AI review.')
        if not busy.acquire(blocking=False):
            abort(409, 'An ESDP review is running. Wait for it to finish.')
        try:
            doc = modules.esdp.extract(body['filename'], base64.b64decode(body.get('data', ''), validate=True))
            return jsonify(modules.esdp.evaluate(doc, body['use_ai']))
        finally:
            busy.release()

    @app.post('/api/assistant/query')
    def query():
        if assistant is None:
            abort(503, 'No RAG/LLM provider is attached.')
        body = request.get_json()
        if not isinstance(body, dict) or body.get('consent') is not True:
            abort(400, 'Confirm sending scoped evidence to the attached provider.')
        tool, team, question = body.get('tool'), body.get('team'), body.get('question')
        if tool not in workspaces or (team is not None and team not in getattr(modules, tool).TEAM_IDS):
            abort(400, 'Choose a valid tool and team scope.')
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
            abort(400, 'Question must contain 1–4000 characters.')
        evidence = list(corpus(workspaces[tool], tool, team))
        result = assistant.answer(question=question.strip(), evidence=evidence)
        ids = {item['id'] for item in evidence}
        if (not isinstance(result, dict) or not isinstance(result.get('answer'), str)
                or not isinstance(result.get('citations'), list)
                or any(not isinstance(c, str) or c not in ids for c in result['citations'])):
            abort(502, 'The provider returned an invalid answer or out-of-scope citation.')
        return jsonify(answer=result['answer'], citations=result['citations'])

    return app
