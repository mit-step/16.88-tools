"""Single-user local PDR feedback workspace. Run with --help for options."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader

import pdr_tool as core

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["Org Chart", "Overview", "Baseline design", "ConOps", "Safety", "Work schedule", "Prototype", "General notes"]
TEAMS = [
    {"id": "hexapod", "name": "Hexapod", "aliases": ["hexapod"], "pilot_page": 2, "color": "#306f86"},
    {"id": "phytogarden", "name": "Phytogarden", "aliases": ["phytogarden", "space garden"], "pilot_page": 3, "color": "#617a48"},
    {"id": "active-textiles", "name": "Active Textiles: Lunar Dust", "aliases": ["active textiles", "activetextiles", "lunar dust team"], "pilot_page": 4, "color": "#946b39"},
    {"id": "lumbar-puncture", "name": "Lumbar Puncture in Weightlessness", "aliases": ["lumbar puncture", "lumbarpuncture"], "pilot_page": 5, "color": "#8c6887"},
    {"id": "catena", "name": "CATENA", "aliases": ["catena"], "pilot_page": 6, "color": "#aa624c"},
    {"id": "vitabee", "name": "VITABee Transfer", "aliases": ["vitabee", "vita bee"], "pilot_page": 7, "color": "#8b8137"},
]
TEAM_IDS = {t["id"] for t in TEAMS}
PILOT_MAPPING = {**{n: "active-textiles" for n in (1, 2, 3, 23)},
                 **{n: "phytogarden" for n in (4, 5, 6, 7)},
                 **{n: "hexapod" for n in (8, 9, 10, 11)},
                 **{n: "lumbar-puncture" for n in (12, 13, 14, 15)},
                 **{n: "catena" for n in (16, 17, 18)},
                 **{n: "vitabee" for n in (19, 21, 22)}}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def match_team(text):
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text or "")
    text = clean(text).casefold().replace("_", " ")
    matches = {t["id"] for t in TEAMS if any(re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", text) for alias in t["aliases"])}
    return next(iter(matches)) if len(matches) == 1 else None


def category(label):
    label = clean(label).casefold()
    for name in CATEGORIES:
        if label.startswith(name.casefold()):
            return name
    return None


def native_comments(page):
    """Read real table columns; never infer scores from X or empty cells."""
    comments = []
    found = False
    for table in page.extract_tables():
        for row in table:
            if len(row) < 4:
                continue
            cat = category(row[0])
            if not cat:
                continue
            found = True
            comments.append({"category": cat, "text": clean(row[3]),
                             "complete": clean(row[1]), "quality": clean(row[2]), "kind": "faculty"})
    text = page.extract_text() or ""
    notes = re.search(r"General\s+notes\s*:\s*(.*)", text, re.I | re.S)
    if notes and clean(notes[1]):
        comments.append({"category": "General notes", "text": clean(notes[1]),
                         "complete": "", "quality": "", "kind": "faculty"})
    if not found and not notes and clean(text):
        comments.append({"category": "General notes", "text": clean(text),
                         "complete": "", "quality": "", "kind": "unstructured"})
    return comments, found


def pilot_baselines(path):
    reader = PdfReader(path)
    result = {}
    for team in TEAMS:
        text = reader.pages[team["pilot_page"] - 1].extract_text()
        text = text.split("DRAFT STUDENT FEEDBACK | Partial evaluation set", 1)[1]
        headline, rest = text.split("Strengths to retain", 1)
        strengths, rest = rest.split("Priorities for CDR", 1)
        rest = rest.split("Sources:", 1)[0]
        priorities = []
        for part in re.split(r"\n\d+\. ", rest)[1:]:
            heading, feedback = part.split("Faculty feedback:", 1)
            feedback, action = feedback.split("Suggested deliverable:", 1)
            priorities.append({"title": clean(heading), "faculty_feedback": clean(feedback), "suggested_action": clean(action)})
        result[team["id"]] = {"headline": clean(headline), "strengths": clean(strengths), "priorities": priorities,
                              "source": "PDR_Feedback_Agent_Pilot.pdf", "page": team["pilot_page"],
                              "label": "Imported pilot draft; not regenerated or independently revalidated"}
    return result


class Workspace:
    def __init__(self, folder, seed=True):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.state_path = self.folder / "workspace.json"
        if self.state_path.exists():
            self.state = core.read(self.state_path)
        else:
            self.state = {"version": 2, "cycle": "Fall 2026 PDR", "documents": [], "baselines": {},
                          "updated": core.stamp(), "events": []}
            if seed:
                pilot = ROOT.parent / "PDR_Feedback_Agent_Pilot.pdf"
                self.state["baselines"] = pilot_baselines(pilot)
                (self.folder / "reference").mkdir(exist_ok=True)
                (self.folder / "reference" / "pilot.pdf").write_bytes(pilot.read_bytes())
                for pdf in sorted((ROOT.parent / "Reviews").glob("*.pdf")):
                    self.ingest(pdf.name, pdf.read_bytes(), seed=True)
            self.save("Workspace initialized")

    def save(self, message):
        if self.state_path.exists():
            core.write(self.folder / "history" / (core.stamp() + ".json"), core.read(self.state_path))
        self.state["updated"] = core.stamp()
        self.state["events"].append({"time": self.state["updated"], "message": message})
        core.write(self.state_path, self.state)

    def ingest(self, filename, data, chosen_team=None, use_ai=False, seed=False):
        filename = Path(filename.replace("\\", "/")).name
        if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
            raise ValueError("Upload a valid PDF file.")
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Maximum file size is 20 MB.")
        if chosen_team and chosen_team not in TEAM_IDS:
            raise ValueError("Unknown team.")
        sha = hashlib.sha256(data).hexdigest()
        with self.lock:
            duplicate = next((d for d in self.state["documents"] if d["id"] == sha), None)
            if duplicate:
                return {"duplicate": True, "document": duplicate["filename"], "message": "Identical PDF already exists; feedback was not counted again."}
            # PDFium is not thread safe: parsing/rendering/mutations share this lock.
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if not 0 < len(pdf.pages) <= 100:
                    raise ValueError("PDF must contain between 1 and 100 pages.")
                folder = self.folder / "files" / sha
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "document.pdf").write_bytes(data)
                rendered = pdfium.PdfDocument(data)
                doc = {"id": sha, "filename": filename, "uploaded": core.stamp(),
                       "origin": "supplied reviews" if seed else "upload", "pages": [],
                       "source_type": "consolidated" if "gradingrubric" in filename.casefold() else "unknown"}
                doc_team = chosen_team or match_team(filename)
                for n, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    team = chosen_team or match_team(text) or doc_team
                    basis = "Selected at upload" if chosen_team else "Name in rubric or filename" if team else "Unidentified"
                    if seed and filename == "PDR_reviews.pdf":
                        team = PILOT_MAPPING.get(n)
                        basis = "Pilot mapping proposal; instructor confirmation needed" if team else "Unidentified; not assigned by adjacency"
                    image_page = rendered[n - 1]
                    bitmap = image_page.render(scale=1.6)
                    png_path = folder / f"page-{n}.png"
                    bitmap.to_pil().save(png_path)
                    bitmap.close()
                    image_page.close()
                    image_area = max((max(0, x["x1"]-x["x0"]) * max(0, x["bottom"]-x["top"]) for x in page.images), default=0)
                    blank = not clean(text) and not page.images and not page.annots
                    scanned = not blank and (len(clean(text)) < 80 or image_area > page.width * page.height * .55)
                    comments, table = ([], False) if scanned else native_comments(page)
                    method = "blank_page" if blank else "scan_pending" if scanned else "native_table" if table else "native_text"
                    limitation = "No text or embedded image found; confirm this page is blank." if blank else "Scan/handwriting has not been transcribed." if scanned else "Text and column extraction need instructor review."
                    if page.annots:
                        limitation += " PDF annotations may contain additional feedback; inspect the original."
                    record = {"number": n, "team": team, "mapping_basis": basis,
                              "verified": False, "method": method, "limitations": limitation,
                              "comments": comments, "text": text, "reviewer": "As listed on original source"}
                    if use_ai:
                        if not self.ai_ready:
                            raise ValueError("AI is not configured. Set OPENAI_API_KEY and PDR_MODEL on the server.")
                        try:
                            extracted = core.ask(os.environ["PDR_MODEL"], core.EXTRACT_PROMPT, [
                                {"type": "input_text", "text": json.dumps({"filename": filename, "page": n, "text_layer": text})},
                                {"type": "input_image", "detail": "high", "image_url": "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode()}], core.Extraction)
                            record["extraction"] = extracted
                            record["reviewer"] = extracted["reviewer_label_as_written"]
                            record["team"] = chosen_team or match_team(extracted["candidate_team"] or "") or team
                            record["comments"] = [{"category": c["category"], "text": c["excerpt"], "complete": c["completeness_mark"],
                                                   "quality": c["quality_mark"], "kind": "faculty", "uncertainty": c["uncertainty"]}
                                                  for c in extracted["comments"]]
                            record["method"] = "ai_vision"
                            record["limitations"] = "AI transcription; verify handwriting, marks, and team identity. " + "; ".join(extracted["page_limitations"])
                        except (ValueError, OSError) as error:
                            record["limitations"] += " AI extraction failed; source retained for retry/manual review."
                            record["ai_error"] = str(error)[:300]
                    doc["pages"].append(record)
                rendered.close()
            self.state["documents"].append(doc)
            self.save(f"{'Imported' if seed else 'Uploaded'} {filename}; {len(doc['pages'])} pages")
            return {"duplicate": False, "document": filename, "pages": len(doc["pages"]),
                    "mapped": sum(bool(p["team"]) for p in doc["pages"]),
                    "pending_scans": sum(p["method"] == "scan_pending" for p in doc["pages"]),
                    "message": "Saved; team summaries updated. All extracted feedback remains a draft."}

    @property
    def ai_ready(self):
        return bool(os.environ.get("OPENAI_API_KEY") and os.environ.get("PDR_MODEL"))

    def page(self, doc_id, number):
        doc = next((d for d in self.state["documents"] if d["id"] == doc_id), None)
        if not doc or not 1 <= number <= len(doc["pages"]):
            raise ValueError("Unknown source page.")
        return doc, doc["pages"][number - 1]

    def mutate_page(self, payload):
        with self.lock:
            doc, page = self.page(payload["document"], int(payload["page"]))
            action = payload["action"]
            if action == "assign":
                team = payload.get("team") or None
                if team and team not in TEAM_IDS:
                    raise ValueError("Unknown team.")
                page.update(team=team, mapping_basis="Instructor-assigned in workspace", verified=False)
            elif action == "note":
                text = clean(payload.get("text", ""))
                cat = payload.get("category")
                if not text or len(text) > 20000 or cat not in CATEGORIES:
                    raise ValueError("Choose a rubric category and enter feedback (maximum 20,000 characters).")
                page["comments"].append({"category": cat, "text": text, "complete": "", "quality": "", "kind": "manual"})
                page["verified"] = False
                if page["method"] == "scan_pending":
                    page["method"] = "manual_partial"
                    page["limitations"] = "Manually transcribed comments added; complete-page coverage still needs confirmation."
            elif action == "verify":
                if payload.get("confirmed") is not True:
                    raise ValueError("Explicit full-page review confirmation is required.")
                if page["method"] in ("scan_pending", "manual_partial"):
                    page["method"] = "manual_reviewed"
                page["verified"] = True
                page["limitations"] = "Page content and mapping marked reviewed locally by the instructor."
            else:
                raise ValueError("Unsupported page action.")
            self.save(f"{action}: {doc['filename']} p. {page['number']}")

    def snapshot(self):
        with self.lock:
            state = json.loads(json.dumps(self.state))
        state.update(teams=TEAMS, categories=CATEGORIES, ai_ready=self.ai_ready, csrf_token=self.token)
        # Aggregate duplicate wording without inventing consensus or losing locators.
        summaries = {}
        for team in TEAMS:
            groups = {c: {} for c in CATEGORIES}
            pages = []
            for doc in state["documents"]:
                for page in doc["pages"]:
                    if page["team"] != team["id"]:
                        continue
                    pages.append(page)
                    for comment in page["comments"]:
                        if not comment["text"]:
                            continue
                        cat = comment["category"] if comment["category"] in groups else "General notes"
                        key = clean(comment["text"]).casefold()
                        entry = groups[cat].setdefault(key, {"text": comment["text"], "sources": []})
                        entry["sources"].append({"document": doc["id"], "filename": doc["filename"],
                                                 "page": page["number"], "row": comment["category"],
                                                 "complete": comment["complete"], "quality": comment["quality"],
                                                 "verified": page["verified"], "uncertainty": comment.get("uncertainty", "")})
            summaries[team["id"]] = {"groups": {c: list(g.values()) for c, g in groups.items()},
                "pages": len(pages), "read_pages": sum(p["method"] not in ("scan_pending", "blank_page") for p in pages),
                "verified_pages": sum(p["verified"] for p in pages),
                "pending_scans": sum(p["method"] == "scan_pending" for p in pages),
                "comments": sum(len(g) for g in groups.values())}
        state["summaries"] = summaries
        return state


class Handler(BaseHTTPRequestHandler):
    server_version = "PDRWorkspace/0.2"

    def send(self, status, data, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        return self.headers.get("Host", "") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "Local workspace only."})
        path = unquote(urlsplit(self.path).path)
        if path == "/api/workspace":
            return self.send(200, self.server.workspace.snapshot())
        if path == "/api/export":
            result = self.server.workspace.snapshot()
            result.pop("csrf_token", None)
            return self.send(200, result)
        if path in ("/", "/app.js", "/style.css"):
            file = ROOT / "web" / ("index.html" if path == "/" else path[1:])
        elif path == "/reference/pilot.pdf":
            file = self.server.workspace.folder / "reference" / "pilot.pdf"
        elif re.fullmatch(r"/files/[a-f0-9]{64}/(document\.pdf|page-\d+\.png)", path):
            file = self.server.workspace.folder / path.lstrip("/")
        else:
            return self.send(404, {"error": "Not found"})
        if not file.is_file():
            return self.send(404, {"error": "Not found"})
        self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")

    def do_POST(self):
        if not self.host_ok() or self.headers.get("X-PDR-Token") != self.server.workspace.token:
            return self.send(403, {"error": "Refresh the local workspace before changing data."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 30 * 1024 * 1024:
                return self.send(413, {"error": "Request is empty or too large (20 MB PDF maximum)."})
            payload = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            if path == "/api/upload":
                data = base64.b64decode(payload["data"], validate=True)
                if payload.get("use_ai") and not self.server.workspace.ai_ready:
                    raise ValueError("AI is not configured; disable AI reading to save the PDF locally.")
                result = self.server.workspace.ingest(payload["filename"], data, payload.get("team"), payload.get("use_ai", False))
            elif path == "/api/page":
                self.server.workspace.mutate_page(payload)
                result = {"message": "Saved; team summary updated."}
            else:
                return self.send(404, {"error": "Not found"})
            self.send(200, result)
        except (ValueError, KeyError, OSError) as error:
            self.send(400, {"error": str(error)[:400]})
        except Exception:
            self.send(400, {"error": "Could not read this PDF. Original workspace data is unchanged; use an unlocked, valid PDF."})

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=ROOT / "workspace-data")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    workspace = Workspace(args.data, seed=not args.no_seed)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.workspace = workspace
    print(f"PDR feedback workspace: http://127.0.0.1:{args.port}", flush=True)
    print(f"Persistent data: {workspace.folder}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
