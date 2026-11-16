import base64
import copy
import io
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from docx import Document
from pypdf import PdfWriter
import esdp_review as core
from app import Server


def sample_docx():
    doc = Document()
    doc.add_paragraph('Experiment overview: This experiment records the motion of sealed samples during altered gravity, using an independent camera.')
    doc.add_table(rows=1, cols=2).rows[0].cells[0].text = 'Batteries: commercial camera, 4 Wh, one spare.'
    doc.add_paragraph('Ground operations: inspect containment before installing the rack.')
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def mock_review(doc):
    return {'summary': 'Fictional test response', 'priority_actions': ['Revise'], 'instructor_questions': ['Inspect diagrams'],
            'rows': [{'criterion_id': c['id'], 'completeness': 'Partial', 'score': 1,
                      'feedback': 'Test observation', 'action': 'Test action',
                      'evidence': [{'unit_id': doc['units'][0]['id'], 'quote': 'This experiment records the motion of sealed samples'}]} for c in core.RUBRIC['criteria']]}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.doc = core.extract('test.docx', sample_docx())

    def test_docx_body_order_and_table(self):
        self.assertEqual(len(self.doc['units']), 3)
        self.assertIn('Batteries:', self.doc['units'][1]['text'])
        self.assertIn('Ground operations:', self.doc['units'][2]['text'])
        self.assertTrue(all('Word body' in u['locator'] for u in self.doc['units']))

    def test_inventory_does_not_grade_or_judge_completeness(self):
        result = core.evaluate(self.doc)
        self.assertEqual(len(result['rows']), 12)
        self.assertIsNone(result['draft_indicator'])
        self.assertTrue(all(r['score'] is None and r['completeness'] == 'Not assessed' for r in result['rows']))

    def test_invalid_and_empty(self):
        for name, data in [('a.txt', b'hello'), ('a.pdf', b'fake'), ('a.docx', b'fake'), ('a.pdf', b'')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.extract(name, data)

    def test_scanned_pdf_not_called_missing_and_ai_blocked(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
        out = io.BytesIO(); writer.write(out)
        doc = core.extract('scan.pdf', out.getvalue())
        self.assertIn('little readable text', ' '.join(doc['warnings']))
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test', 'ESDP_MODEL':'test'}), patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError, 'Incomplete text'):
                core.ai_review(doc)
            request.assert_not_called()

    def test_citation_validation(self):
        review = mock_review(self.doc)
        self.assertEqual(len(core.validate_review(review, self.doc)['rows']), 12)
        for change in ('quote', 'unit_id'):
            bad = copy.deepcopy(review); bad['rows'][0]['evidence'][0][change] = 'fabricated evidence'
            with self.assertRaises(ValueError): core.validate_review(bad, self.doc)

    def test_missing_duplicate_and_score_validation(self):
        value = mock_review(self.doc)
        for rows in (value['rows'][:-1], value['rows'] + [value['rows'][0]]):
            with self.assertRaises(ValueError): core.validate_review({**value, 'rows':rows}, self.doc)
        value['rows'][0]['score'] = 3
        with self.assertRaises(ValueError): core.validate_review(value, self.doc)
        value = mock_review(self.doc); value['rows'][0]['evidence'] = []
        with self.assertRaises(ValueError): core.validate_review(value, self.doc)

    def test_ai_protocol_mocked(self):
        response = {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(mock_review(self.doc))}]}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test-key','ESDP_MODEL':'test-model'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result = core.evaluate(self.doc, True)
            self.assertEqual(result['draft_indicator'], 33.3)
            payload = json.loads(request.call_args.args[0].data)
            self.assertFalse(payload['store'])
            self.assertTrue(payload['text']['format']['strict'])
            self.assertIn('UNTRUSTED DATA', payload['input'][0]['content'])

    def test_ai_incomplete_refused_rejected(self):
        for response in ({'status':'incomplete'}, {'status':'completed','output':[{'content':[{'type':'refusal'}]}]}):
            with patch.dict(os.environ, {'OPENAI_API_KEY':'test','ESDP_MODEL':'test'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ValueError): core.ai_review(self.doc)

    def test_unassessable_withholds_indicator_and_na_excludes(self):
        review = mock_review(self.doc)
        review['rows'][0].update(completeness='Not assessable', score=None)
        with patch.object(core, 'ai_review', return_value=review):
            self.assertIsNone(core.evaluate(self.doc, True)['draft_indicator'])
        review['rows'][0].update(completeness='Not applicable', score=None)
        with patch.object(core, 'ai_review', return_value=review):
            result = core.evaluate(self.doc, True)
            self.assertEqual(result['assessed_weight'], 95)
            self.assertEqual(result['draft_indicator'], 33.3)

    def test_examples_full_extraction(self):
        for path in (core.ROOT / 'ESDP Examples').iterdir():
            with self.subTest(file=path.name):
                doc = core.extract(path.name, path.read_bytes())
                self.assertGreater(doc['characters'], 20000)
                self.assertEqual(len(core.evaluate(doc)['rows']), 12)
                if path.suffix == '.pdf': self.assertEqual(len(doc['units']), 28)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(('127.0.0.1',0))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, payload, token=True, origin=None):
        headers = {'Content-Type':'application/json'}
        if token: headers['X-ESDP-Token'] = self.server.token
        if origin: headers['Origin'] = origin
        return urllib.request.urlopen(urllib.request.Request(self.url+'/api/review',data=json.dumps(payload).encode(),headers=headers))

    def test_config_and_full_upload(self):
        with urllib.request.urlopen(self.url+'/api/config') as response:
            self.assertEqual(json.load(response)['token'], self.server.token)
        payload = {'filename':'test.docx','data':base64.b64encode(sample_docx()).decode(),'use_ai':False}
        with self.request(payload) as response:
            self.assertEqual(json.load(response)['mode'], 'Local section inventory')

    def test_csrf_origin_and_consent(self):
        for token, origin, payload, expected in [(False,None,{},403),(True,'http://evil.example',{},403),(True,None,{'filename':'a.pdf','use_ai':True},400)]:
            with self.assertRaises(urllib.error.HTTPError) as error: self.request(payload,token,origin)
            self.assertEqual(error.exception.code,expected)

    def test_foreign_host_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(self.url,headers={'Host':'evil.example'}))
        self.assertEqual(error.exception.code,403)


if __name__ == '__main__': unittest.main()
