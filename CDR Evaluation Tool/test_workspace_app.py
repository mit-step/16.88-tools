"""Workspace integration tests use temporary storage; real workspace is untouched."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from pypdf import PdfReader, PdfWriter
import workspace_app as app


def fixture_pdf():
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    output = io.BytesIO()
    rows = [["CATENA CDR", "Complete?", "Notes"],
            ["Catchy or communicative title", "X", "A fictional title comment."],
            ["Updated Org Chart", "X", ""],
            ["Overview", "", "Define success."],
            ["Final design", "?", "Show mounting calculations."],
            ["ConOps", "", "Show task sequence."],
            ["Safety", "", "Check double containment."],
            ["Work schedule", "", "Add integration tests."],
            ["Updated Budget", "X", "Include shipping."],
            ["Intended output", "", "Choose a video or paper."],
            ["Prototype", "X", "Sensors record."],
            ["General notes", "Synthetic fixture only.", ""]]
    table = Table(rows, colWidths=[230,60,200])
    table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.black), ("SPAN",(1,-1),(2,-1))]))
    SimpleDocTemplate(output).build([table])
    return output.getvalue()

FIXTURE_BYTES = fixture_pdf()

class Fixture:
    name = "CATENA_CDR_test.pdf"
    def read_bytes(self): return FIXTURE_BYTES
SOURCE = Fixture()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = app.Workspace(self.temp.name, seed=False)

    def tearDown(self):
        self.temp.cleanup()

    def ingest(self):
        return self.workspace.ingest(SOURCE.name, SOURCE.read_bytes())

    def test_team_matching_handles_aliases_camel_case_and_ambiguity(self):
        self.assertEqual(app.match_team("ActiveTextilesLunarDust_CDR.pdf"), "active-textiles")
        self.assertEqual(app.match_team("Space Garden"), "phytogarden")
        self.assertEqual(app.match_team("LumbarPuncture_CDR.pdf"), "lumbar-puncture")
        self.assertIsNone(app.match_team("CATENA and Hexapod"))
        self.assertIsNone(app.match_team("Unnamed team"))

    def test_native_columns_general_notes_and_automatic_summary(self):
        result = self.ingest()
        snapshot = self.workspace.snapshot()
        self.assertEqual(result["mapped"], 1)
        page = snapshot["documents"][0]["pages"][0]
        self.assertEqual(page["method"], "native_table")
        safety = next(c for c in page["comments"] if c["category"] == "Safety")
        self.assertEqual(safety["complete"], "")
        self.assertIn("double containment", safety["text"])
        self.assertEqual(snapshot["summaries"]["catena"]["comments"], 10)
        self.assertIn("Synthetic fixture", snapshot["summaries"]["catena"]["groups"]["General notes"][0]["text"])
        self.assertFalse(page["verified"])

    def test_duplicate_file_does_not_change_summary_or_history(self):
        self.ingest()
        before = copy.deepcopy(self.workspace.state)
        result = self.ingest()
        self.assertTrue(result["duplicate"])
        self.assertEqual(self.workspace.state, before)

    def test_added_review_updates_summary_without_duplicating_wording(self):
        self.ingest()
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(SOURCE.read_bytes())))
        writer.add_metadata({"/Title": "Different upload, same words"})
        output = io.BytesIO()
        writer.write(output)
        self.workspace.ingest("CATENA_followup.pdf", output.getvalue())
        summary = self.workspace.snapshot()["summaries"]["catena"]
        self.assertEqual(summary["pages"], 2)
        self.assertEqual(summary["comments"], 10)
        self.assertEqual(len(summary["groups"]["Safety"][0]["sources"]), 2)

    def test_unknown_blank_pdf_is_quarantined_not_counted_as_handwritten_scan(self):
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        output = io.BytesIO()
        writer.write(output)
        self.workspace.ingest("Unknown.pdf", output.getvalue())
        page = self.workspace.state["documents"][0]["pages"][0]
        self.assertIsNone(page["team"])
        self.assertEqual(page["method"], "blank_page")

    def test_manual_note_updates_summary_and_review_requires_confirmation(self):
        self.ingest()
        doc_id = self.workspace.state["documents"][0]["id"]
        payload = dict(document=doc_id, page=1)
        self.workspace.mutate_page(dict(**payload, action="note", category="Safety", text="A fictional test-only comment."))
        self.assertEqual(self.workspace.snapshot()["summaries"]["catena"]["comments"], 11)
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.workspace.mutate_page(dict(**payload, action="verify", confirmed=False))
        self.workspace.mutate_page(dict(**payload, action="verify", confirmed=True))
        self.assertEqual(self.workspace.snapshot()["summaries"]["catena"]["verified_pages"], 1)
        self.workspace.mutate_page(dict(**payload, action="assign", team="hexapod"))
        summary = self.workspace.snapshot()["summaries"]
        self.assertEqual(summary["catena"]["comments"], 0)
        self.assertEqual(summary["hexapod"]["comments"], 11)
        self.assertEqual(summary["hexapod"]["verified_pages"], 0)

    def test_cdr_criteria_and_literal_marks(self):
        self.ingest()
        page = self.workspace.state["documents"][0]["pages"][0]
        self.assertEqual(len(page["comments"]), 11)
        design = next(c for c in page["comments"] if c["category"] == "Final design")
        self.assertEqual(design["complete"], "?")
        self.assertEqual(design["quality"], "")
        self.assertIn("Title and one-liner", self.workspace.snapshot()["categories"])
        self.assertEqual(self.workspace.state["baselines"], {})

    def test_checklist_validation_persistence_and_separation(self):
        payload = dict(team="catena", criterion="Final design", status="Needs follow-up", note="Demo observed; see drawing A.")
        self.workspace.assess(payload)
        restarted = app.Workspace(self.temp.name)
        self.assertEqual(restarted.snapshot()["assessments"]["catena"]["Final design"]["status"], "Needs follow-up")
        self.assertEqual(restarted.snapshot()["summaries"]["catena"]["comments"], 0)
        for change in [dict(team="unknown"), dict(criterion="Baseline design"), dict(status="Passed")]:
            with self.assertRaises(ValueError): self.workspace.assess({**payload, **change})

    def test_restart_preserves_docs_and_notes(self):
        self.ingest()
        restarted = app.Workspace(self.temp.name, seed=False)
        self.assertEqual(restarted.state, self.workspace.state)

    def test_non_pdf_and_bad_team_are_rejected(self):
        with self.assertRaises(ValueError):
            self.workspace.ingest("credential.pem", b"not a pdf")
        with self.assertRaises(ValueError):
            self.workspace.ingest(SOURCE.name, SOURCE.read_bytes(), chosen_team="nonexistent")


class HttpTests(unittest.TestCase):
    def test_upload_and_summary_through_http_with_csrf(self):
        with tempfile.TemporaryDirectory() as folder:
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            server.workspace = app.Workspace(folder, seed=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                snapshot = json.load(urllib.request.urlopen(base + "/api/workspace"))
                payload = json.dumps({"filename": SOURCE.name, "data": base64.b64encode(SOURCE.read_bytes()).decode()}).encode()
                request = urllib.request.Request(base + "/api/upload", data=payload, headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 403)
                request.add_header("X-CDR-Token", snapshot["csrf_token"])
                result = json.load(urllib.request.urlopen(request))
                self.assertEqual(result["mapped"], 1)
                assessment = urllib.request.Request(base + "/api/assessment", data=json.dumps({"team":"catena", "criterion":"Updated Budget", "status":"Needs follow-up", "note":"Synthetic HTTP test"}).encode(), headers={"Content-Type":"application/json", "X-CDR-Token":snapshot["csrf_token"]})
                self.assertIn("saved", json.load(urllib.request.urlopen(assessment))["message"])
                current = json.load(urllib.request.urlopen(base + "/api/workspace"))
                self.assertEqual(current["assessments"]["catena"]["Updated Budget"]["status"], "Needs follow-up")
                self.assertTrue(urllib.request.urlopen(base + "/reference/assignment.pdf").read().startswith(b"%PDF-"))
                self.assertTrue(urllib.request.urlopen(base + "/reference/rubric.docx").read().startswith(b"PK"))
                summary = json.load(urllib.request.urlopen(base + "/api/workspace"))["summaries"]["catena"]
                self.assertEqual(summary["comments"], 10)
                source = urllib.request.urlopen(base + f"/files/{server.workspace.state['documents'][0]['id']}/document.pdf")
                self.assertTrue(source.read().startswith(b"%PDF-"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
