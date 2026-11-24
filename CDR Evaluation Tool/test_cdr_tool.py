"""Offline regression tests. Fictional fixtures, never actual student feedback."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cdr_tool as tool


def fixture():
    comment = dict(physical_row="Safety", category="Safety", completeness_mark="X",
                   quality_mark="", excerpt="How will loose items be contained?",
                   observation_type="question", uncertainty="", safety_related=True, substantive=True)
    extraction = dict(candidate_team="Example", mapping_basis="Written title", mapping_confidence="high",
                      reviewer_label_as_written="Reviewer A", source_type="individual",
                      possible_derived_source="", page_limitations=[], comments=[comment])
    page = dict(id="source-p1", filename="fictional.pdf", source_sha256="abc", page=1,
                team="Example", extraction=extraction, review=None)
    page["review"] = dict(by="Human", fingerprint=tool.extraction_fingerprint(page))
    state = dict(cycle="Example only", pages=[page])
    claim = dict(text=comment["excerpt"], evidence_ids=["source-p1-c1"])
    draft = dict(team="Example", coverage_limitations="One fictional sheet.", strengths=[],
                 priorities=[dict(title="Containment", faculty_feedback=[claim],
                                  suggested_deliverables=["Propose a containment test for instructor review."])],
                 unresolved_questions_and_disagreements=[], additional_observations=[])
    return state, draft


class AuditTests(unittest.TestCase):
    def test_complete_citation_is_only_ready_for_content_review(self):
        state, draft = fixture()
        result = tool.audit(state, draft)
        self.assertFalse(result["errors"])
        self.assertEqual(result["status"], "READY FOR INSTRUCTOR CONTENT REVIEW")

    def test_missing_safety_even_with_positive_mark_blocks(self):
        state, draft = fixture()
        draft["priorities"] = []
        result = tool.audit(state, draft)
        self.assertEqual(result["missed_safety_ids"], ["source-p1-c1"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_other_team_citation_blocks(self):
        state, draft = fixture()
        draft["priorities"][0]["faculty_feedback"][0]["evidence_ids"] = ["other-team-p1-c1"]
        self.assertTrue(any("other-team" in e for e in tool.audit(state, draft)["errors"]))

    def test_changed_extraction_invalidates_human_review_and_draft(self):
        state, draft = fixture()
        old_hash = tool.digest(tool.evidence(state, "Example"))
        state["pages"][0]["extraction"]["comments"][0]["excerpt"] = "Changed content"
        errors = tool.audit(state, draft, old_hash)["errors"]
        self.assertTrue(any("human verification" in e for e in errors))
        self.assertTrue(any("Evidence changed" in e for e in errors))

    def test_unread_page_blocks_cycle_coverage(self):
        state, draft = fixture()
        page = copy.deepcopy(state["pages"][0])
        page.update(id="unread-p1", team=None, review=None, extraction=None)
        state["pages"].append(page)
        self.assertTrue(any("unread-p1" in e for e in tool.audit(state, draft)["errors"]))

    def test_quarantined_page_does_not_become_team_evidence(self):
        state, draft = fixture()
        page = copy.deepcopy(state["pages"][0])
        page.update(id="unknown-p1", team=None)
        page["review"]["fingerprint"] = tool.extraction_fingerprint(page)
        state["pages"].append(page)
        self.assertEqual(len(tool.evidence(state, "Example")), 1)
        self.assertFalse(tool.audit(state, draft)["errors"])

    def test_conflicting_records_require_both_citations(self):
        state, draft = fixture()
        comment = copy.deepcopy(state["pages"][0]["extraction"]["comments"][0])
        comment["excerpt"] = "Consider a net if recovery is assured."
        state["pages"][0]["extraction"]["comments"].append(comment)
        state["pages"][0]["review"]["fingerprint"] = tool.extraction_fingerprint(state["pages"][0])
        self.assertIn("source-p1-c2", tool.audit(state, draft)["omitted_evidence_ids"])

    def test_report_escapes_source_markup(self):
        state, draft = fixture()
        draft["team"] = "<script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "draft.html"
            tool.render_draft(path, draft, tool.evidence(state, "Example"), {"status": "BLOCKED"})
            output = path.read_text(encoding="utf-8")
            self.assertNotIn("<script>", output)
            self.assertIn("&lt;script&gt;", output)


class ApiAdapterTests(unittest.TestCase):
    def test_structured_response_and_no_storage(self):
        _, draft = fixture()
        result = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(draft)}]}]}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(result).encode()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fictional-test-key"}), \
                patch("urllib.request.urlopen", return_value=Response()) as request:
            actual = tool.ask("configured-model", "instructions", [], tool.Draft)
            body = json.loads(request.call_args.args[0].data)
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(actual, draft)

    def test_refusal_is_not_saved_as_output(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'{"status":"completed","output":[{"content":[{"type":"refusal"}]}]}'
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fictional-test-key"}), \
                patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(ValueError, "refused"):
                tool.ask("configured-model", "instructions", [], tool.Draft)


class PrepareTests(unittest.TestCase):
    def test_real_pdf_deduplication_and_existing_run_protection(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            source.mkdir()
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with (source / "original.pdf").open("wb") as stream:
                writer.write(stream)
            (source / "duplicate.pdf").write_bytes((source / "original.pdf").read_bytes())
            (source / "unrelated-secret.pem").write_text("not a pdf")
            run = root / "run"
            tool.prepare(source, run, "Test cycle")
            state = tool.read(run / "state.json")
            self.assertEqual(len(state["documents"]), 1)
            self.assertEqual(len(state["duplicates"]), 1)
            self.assertEqual(len(state["pages"]), 1)
            self.assertTrue((run / state["pages"][0]["image"]).exists())
            self.assertIsNone(state["pages"][0]["team"])
            self.assertIsNone(state["pages"][0]["review"])
            with self.assertRaisesRegex(ValueError, "existing runs"):
                tool.prepare(source, run, "Test cycle")


if __name__ == "__main__":
    unittest.main()
