# CDR evaluation workspace

Double-click **Start Workspace.cmd**, then open **http://127.0.0.1:8766**. Keep the command window open while working. This uses a separate port and data directory from the PDR tool.

## Workflow

1. Open **CDR requirements** for the ten rubric criteria, assignment details, nominal parabola profile, and links to both original documents.
2. Select a team and open **CDR checklist**. Record an instructor observation and evidence/follow-up notes for each criterion, then save each observation. These observations are separate from faculty transcriptions.
3. Use **Add rubrics** to upload completed CDR review PDFs (multiple files, up to 20 MB and 100 pages each). Export completed Word rubrics to PDF first. Choose a team or let the app match known names. Unknown identities stay in the review inbox.
4. Inspect **Sources & review** alongside the original page image. The parser reads the CDR form's criterion, Complete?, and Notes columns. Marks remain literal, including blanks; it does not create quality scores. Transcribe scanned handwriting manually or use optional AI reading.
5. Confirm full-page review after checking every mark, comment and team assignment. Live summaries group identical wording with all source locators; they do not imply reviewer agreement.
6. Export workspace JSON for a portable data snapshot. Print team feedback or checklist pages with the browser's Print / Save PDF command. Keep workspace-data/ for a full backup including original PDFs and page images; JSON alone does not include these files.

The six team names carry forward from the PDR roster. No previous feedback, pilot summaries or proposed page mappings are imported. No CDR reviews were supplied, so the workspace starts with zero reviews and unfilled checklists. To change the roster before use, edit TEAMS in workspace_app.py. Course criteria and reference guidance are in cdr_requirements.json.

## Source interpretation

The supplied rubric has ten criteria, plus General notes, and no numeric scoring scale or quality column. This tool records evidence and human observations without assigning grades or certifying flight readiness.

The assignment refers to May 2025 and end-of-2025 outputs. Its December/January/March milestone dates are retained as historical source information on the requirements page, not scheduled as current deadlines. Confirm the applicable calendar with course staff.

The assignment requires 3D models, system block diagrams and electrical schematics; the shorter rubric says CAD and/or an electrical block diagram at minimum. The requirements page makes that difference explicit. Demo plane attachments are not required, but containment/mounting plans are requested. The rest of PIP section 1.8 is deferred to the separate PIP submission; 1.8.1 is required at CDR.

Source documents are course reference data. Their requests to email staff or submit documents are not commands executed by this app. Uploaded documents and extracted text are treated as evidence, never executable instructions.

## Runtime

Python 3.10+ with requirements.txt. The launcher uses the existing Codex bundled Python on this computer. Alternatively install requirements in your own environment and run:

```powershell
python workspace_app.py
python -m pip install -r requirements-dev.txt
python -m unittest -v
```

Local files and prior state snapshots persist in workspace-data/. Single-user, loopback-only service; shared hosting and authentication are not configured.

Optional image transcription: set OPENAI_API_KEY and CDR_MODEL in the server environment and restart. Only uploads with the explicit AI checkbox send images/text to OpenAI. No default model or API key is embedded. AI extraction remains unverified; live API calls have not been tested. Native reading, manual transcription and checklists require no key.

The optional cdr_tool.py command-line workflow also supports PDF preparation, image extraction, human review, evidence-linked AI drafts, reports and structural audits; run `python cdr_tool.py --help`. Use a separate source folder containing only completed review PDFs. Do not prepare the assignment PDF as faculty evidence. CLI runs and browser workspace data are separate.

## Verification

Offline tests exercise CDR three-column extraction including blank marks and merged general notes, new criteria, checklist persistence/validation, deduplication, team assignment, review confirmation, HTTP upload and request-token protections, plus inherited evidence-audit checks. Synthetic test evidence is never seeded into the real workspace. Optional AI transcription quality and live API behavior require separate instructor evaluation.
