import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from flask.testing import FlaskClient
from review_suite.app import create_app
from review_suite import modules


class BufferedClient(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs.setdefault('buffered', True)
        return super().open(*args, **kwargs)


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'TESTING': True, 'DATA_DIR': self.temp.name, 'IMPORT_LEGACY': False}
        self.app = create_app(self.config)
        self.app.test_client_class = BufferedClient
        self.client = self.app.test_client()

    def token(self, tool):
        if tool == 'esdp':
            return self.client.get('/tools/esdp/api/config').json['token']
        return self.client.get(f'/tools/{tool}/api/workspace').json['csrf_token']

    def post(self, tool, action, body):
        return self.client.post(f'/tools/{tool}/api/{action}', json=body,
                                headers={f'X-{tool.upper()}-Token': self.token(tool)})

    def test_shell_assets_and_namespaced_links(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for tool in ('pdr', 'cdr', 'esdp'):
            html = self.client.get(f'/tools/{tool}/').text
            self.assertIn(f'/tools/{tool}/app.js', html)
            js = self.client.get(f'/tools/{tool}/app.js').text
            self.assertNotIn("fetch('/api/", js)
            self.assertIn(f'/tools/{tool}/api/', js)
        self.assertEqual(self.client.get('/tools/cdr/reference/assignment.pdf').status_code, 200)
        self.assertEqual(self.client.get('/tools/pdr/files/../workspace.json').status_code, 404)

    def test_mutation_security(self):
        self.assertEqual(self.client.post('/tools/pdr/api/upload', json={}).status_code, 403)
        response = self.client.post('/tools/cdr/api/upload', json={},
            headers={'X-CDR-Token': self.token('cdr'), 'Origin': 'https://attacker.example'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/', headers={'Host': 'attacker.example'}).status_code, 403)
        self.assertEqual(self.post('pdr', 'upload', {'filename':'x.pdf','data':'%%%'}).status_code, 400)
        self.assertEqual(self.post('pdr', 'upload', []).status_code, 400)

    def test_checklist_persists_without_cross_tool_changes(self):
        criterion = modules.cdr.CATEGORIES[0]
        result = self.post('cdr', 'assessment', {'team':'catena','criterion':criterion,
                         'status':'Needs follow-up','note':'Confirm cable restraint.'})
        self.assertEqual(result.status_code, 200, result.text)
        restarted = create_app(self.config).test_client()
        state = restarted.get('/tools/cdr/api/workspace').json
        self.assertEqual(state['assessments']['catena'][criterion]['note'], 'Confirm cable restraint.')
        self.assertNotIn('catena', restarted.get('/tools/pdr/api/workspace').json.get('assessments', {}))
        self.assertNotIn('csrf_token', restarted.get('/tools/cdr/api/export').json)

    def test_upload_review_export_and_source_isolation(self):
        from pypdf import PdfWriter
        writer = PdfWriter(); writer.add_blank_page(width=612, height=792)
        output = io.BytesIO(); writer.write(output)
        body = {'filename':'CATENA.pdf','data':base64.b64encode(output.getvalue()).decode(),
                'team':'catena','use_ai':False}
        for tool in ('pdr','cdr'):
            response = self.post(tool, 'upload', body)
            self.assertEqual(response.status_code, 200, response.text)
            state = self.client.get(f'/tools/{tool}/api/workspace').json
            doc = state['documents'][0]
            self.assertEqual(self.client.get(f"/tools/{tool}/files/{doc['id']}/document.pdf").status_code, 200)
            response = self.post(tool, 'page', {'document':doc['id'],'page':1,'action':'assign','team':'catena'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(self.client.get(f'/tools/{tool}/api/export').json['documents']),1)

    def test_esdp_local_and_ai_consent(self):
        doc = Document(); doc.add_heading('Experiment objectives', 0)
        doc.add_paragraph('Test a contained fluid transfer experiment in reduced gravity.')
        output = io.BytesIO(); doc.save(output)
        body = {'filename':'example.docx','data':base64.b64encode(output.getvalue()).decode(), 'use_ai':False}
        response = self.post('esdp', 'review', body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json['rows']),12)
        body['use_ai'] = True
        with patch.object(modules.esdp, 'evaluate') as evaluate:
            self.assertEqual(self.post('esdp','review',body).status_code,400)
            evaluate.assert_not_called()

    def test_hosted_access_proxy_logout_and_host_validation(self):
        hosted = create_app({**self.config, 'PUBLIC_ORIGIN':'https://reviews.example.edu',
                             'ACCESS_TOKEN':'a-long-shared-workspace-test-code','TRUST_PROXY':True})
        hosted.test_client_class = BufferedClient
        client = hosted.test_client()
        proxy = {'Host':'reviews.example.edu','X-Forwarded-Proto':'https'}
        self.assertIn('Workspace access code',client.get('/',headers=proxy).text)
        self.assertEqual(client.get('/suite/suite.css',headers=proxy).mimetype,'text/css')
        self.assertEqual(client.get('/tools/cdr/api/workspace',headers=proxy).status_code,401)
        self.assertEqual(client.get('/tools/cdr/reference/assignment.pdf',headers=proxy).mimetype,'text/html')
        response = client.post('/login',data={'token':'a-long-shared-workspace-test-code'},headers=proxy)
        self.assertEqual(response.status_code,302)
        self.assertIn('Secure',response.headers['Set-Cookie'])
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        config = client.get('/api/config',headers=proxy).json
        self.assertEqual(client.get('/tools/cdr/api/workspace',headers=proxy).status_code,200)
        self.assertEqual(client.get('/',headers={'Host':'evil.example','X-Forwarded-Proto':'https'}).status_code,403)
        client.post('/api/logout',headers={**proxy,'X-Review-Token':config['csrf_token']})
        self.assertEqual(client.get('/api/config',headers=proxy).status_code,401)
        with self.assertRaises(ValueError):
            create_app({**self.config,'PUBLIC_ORIGIN':'https://reviews.example.edu','ACCESS_TOKEN':''})

    def test_legacy_copy_is_once_and_leaves_original_untouched(self):
        legacy = Path(self.temp.name) / 'legacy'
        original = modules.pdr.Workspace(legacy,seed=False)
        contents = original.state_path.read_bytes()
        with patch.object(modules.pdr,'ROOT',legacy.parent / 'fake-module'):
            # Model the actual source layout: <module>/workspace-data.
            source = modules.pdr.ROOT / 'workspace-data'
            source.mkdir(parents=True)
            (source / 'workspace.json').write_bytes(contents)
            target = Path(self.temp.name) / 'imported'
            app = create_app({**self.config,'DATA_DIR':str(target),'IMPORT_LEGACY':True})
            app.extensions['workspaces']['pdr'].state['cycle'] = 'Changed copy'
            app.extensions['workspaces']['pdr'].save('test')
            restarted = create_app({**self.config,'DATA_DIR':str(target),'IMPORT_LEGACY':True})
            self.assertEqual(restarted.extensions['workspaces']['pdr'].state['cycle'],'Changed copy')
            self.assertEqual((source/'workspace.json').read_bytes(),contents)

    def test_assistant_disabled_and_scoped_provider_contract(self):
        token = self.client.get('/api/config').json['csrf_token']
        self.assertEqual(self.client.post('/api/assistant/query',json={},headers={'X-Review-Token':token}).status_code,503)
        class FakeProvider:
            def answer(self, *, question, evidence):
                self.evidence = evidence
                return {'answer':'Instructor review needed.','citations':[]}
        provider = FakeProvider()
        app = create_app(self.config,assistant=provider); client = app.test_client()
        workspace = app.extensions['workspaces']['cdr']
        workspace.state['documents'] = [
            {'id':'a'*64,'filename':'example.pdf','pages':[
                {'number':1,'team':'catena','verified':False,'comments':[{'text':'Check the enclosure.'}]},
                {'number':2,'team':'hexapod','verified':True,'comments':[{'text':'Other team evidence.'}]},
            ]}]
        # corpus() consumes the evidence ledger; summary generation expects full pages.
        snapshot = {'documents': workspace.state['documents']}
        token = client.get('/api/config').json['csrf_token']
        headers = {'X-Review-Token':token}
        body = {'question':'What needs review?','tool':'cdr','team':'catena','consent':True}
        with patch.object(workspace,'snapshot',return_value=snapshot):
            self.assertEqual(client.post('/api/assistant/query',json=body,headers=headers).status_code,200)
        self.assertEqual(len(provider.evidence),1)
        self.assertEqual(provider.evidence[0]['team'],'catena')
        self.assertEqual(provider.evidence[0]['id'],'cdr:'+'a'*64+':1:0')
        self.assertFalse(provider.evidence[0]['reviewed'])
        body['consent'] = False
        self.assertEqual(client.post('/api/assistant/query',json=body,headers=headers).status_code,400)
        body.update(consent=True,team='unknown')
        self.assertEqual(client.post('/api/assistant/query',json=body,headers=headers).status_code,400)
        body['team']='catena'
        with patch.object(workspace,'snapshot',return_value=snapshot), patch.object(provider,'answer',return_value={'answer':'Unsupported','citations':['pdr:other-team:1:0']}):
            self.assertEqual(client.post('/api/assistant/query',json=body,headers=headers).status_code,502)


if __name__ == '__main__':
    unittest.main()
