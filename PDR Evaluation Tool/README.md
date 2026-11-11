# PDR feedback evaluation prototype

## Browser workspace: team summaries and uploads

Double-click **Start Workspace.cmd** in this folder, then open **http://127.0.0.1:8765**. The command window must remain open while you work. To start directly, run the bundled Python with `workspace_app.py`. This is a single-user local application; no hosting or shared sign-in is configured.

The browser workspace is now the easiest way to use the prototype:

- Six team pages contain the pilot's existing narrative summaries, clearly labeled as imported baseline drafts.
- A separate **live summary** groups actual extracted faculty comments by rubric category, with original PDF/page/row locators. It updates automatically when readable PDFs or manually transcribed comments are added.
- **Add rubrics** accepts multiple PDFs, up to 20 MB and 100 pages each. Existing team names/aliases in the rubric or filename drive matching; you may select a team explicitly. Exact duplicate files are skipped. Unknown identities go to the review inbox.
- Native rubric tables are read locally, including separate completeness and quality columns. Marks are retained literally; grades and reviewer consensus are not inferred.
- Scanned sheets are stored and organized using the pilot's provisional mapping where available. They are not claimed as newly transcribed evidence. The unnamed sheet remains quarantined. Blank pages also need review, but are not counted as scans.
- **Sources & review** shows the original page image, supports correcting team assignment, adding manually transcribed faculty comments, and explicitly marking full-page review. The live summary includes drafts and displays review status.
- **Export data** saves the workspace as JSON. Team pages support browser printing/PDF saving. Original PDFs, page images, workspace state, and previous state snapshots persist in `workspace-data/` after a restart.

No key is required for readable PDF extraction, team organization, summary updates, or manual scan transcription. For optional automatic image/handwriting reading, configure `OPENAI_API_KEY` and `PDR_MODEL` in the server environment, restart the app, then select the AI checkbox when uploading. Only that option sends page images/text to OpenAI, and API charges may apply. AI failures leave sources available for manual review. Live AI calls have not been tested in this session. To retry an existing scan with AI, use the earlier CLI in a separate run; the browser skips duplicate PDF uploads.

The live summary is an extractive grouping of faculty comments, not a newly generated narrative or ranked evaluation. The pilot's historical priority narrative stays separate rather than being silently rewritten on upload. For richer AI-generated priorities, the CLI drafting workflow below remains available. Automatic semantic reconciliation, validated grading, and shared deployment are future work.

For the remainder of the tool, provide a verified team/reviewer roster, an API model/key for handwriting, instructor-adjudicated examples for fidelity evaluation, and scoring rules only if numerical grading is desired. A shared service additionally needs hosting/access and retention decisions. No additional information is needed to use the local summary tool now.

### Available AWS hosting

The supplied `README - AWS Server.docx` describes an existing AWS server, per-app subdomains, Nginx reverse proxying, TLS, and optional app-level MIT Touchstone/SAML registration. That server can be the shared-hosting destination. No server connection, credential use, email, domain registration, or deployment has been performed.

Before moving this local prototype there, choose the application subdomain and intended users, confirm whether Touchstone is required, and choose persistent storage/backups and document-retention rules. The current server deliberately accepts only loopback hosts and uses Python's development HTTP server; a deployment implementation must replace that serving layer with an appropriate application server, configured public hostname/proxy handling, authentication/access controls, durable storage, and runtime secret configuration. Keep credentials outside the app source and uploaded-document store.

## Earlier command-line workflow

Turns faculty PDR review PDFs into a reviewable evidence workspace and, optionally, team feedback drafts. Based on the workflow on pages 8–9 of the supplied pilot. This implements a first local prototype; it has not been benchmarked for handwriting accuracy or faculty-feedback fidelity.

## What is implemented

- Local PDF inventory, SHA-256 file deduplication, copied sources, text extraction, and full-page images.
- Per-page structured AI extraction with literal rubric marks, physical row versus semantic category, reviewer labels, uncertain handwriting, and proposed team identity.
- Human page verification and canonical team assignment; unidentified pages remain quarantined. AI cannot mark its own extraction as verified.
- Per-team AI drafts with cited faculty feedback separate from assistant-suggested deliverables. Up to five priorities plus additional observations prevent silently dropping comments.
- Deterministic audits for unknown/other-team citations, omitted substantive comments, unrepresented safety evidence, unverified pages, and changed evidence. Whole-cycle page verification is required for a clean structural audit.
- HTML evidence workspace and draft reports, with historical state snapshots and separately versioned drafts.

Every output remains an instructor-review draft. There is no grading, readiness certification, student messaging, or release command. Citation presence is a structural check; it cannot establish that a claim is actually supported. Disagreement detection and semantic fidelity still require instructor review.

## Start locally (PowerShell)

From this folder, use Python 3.10+ and install `requirements.txt`. The Codex bundled Python already has these dependencies on this machine:

```powershell
$pdrPython = 'C:\Users\never\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pdrPython pdr_tool.py --help
& $pdrPython -m unittest -v
```

The supplied reviews have already been prepared in `runs/fall2026-pdr`; open `runs/fall2026-pdr/index.html`. This contains 7 unique PDFs and 32 pages. No AI extraction or human verification is claimed for this prepared workspace. The pilot's stated ten consolidated pages differs from the nine pages found in the supplied six consolidated PDFs.

To start a new cycle (use a new run directory):

```powershell
& $pdrPython pdr_tool.py prepare --source '..\Reviews' --run 'runs\new-cycle' --cycle 'Fall 2026 PDR'
```

Only PDFs directly in the specified source folder are read. The pilot PDF is a specification, not original faculty evidence. No deployment credentials or tutorial files are used.

## Optional AI extraction and drafting

`prepare`, `report`, `review`, `audit`, and tests are local. Only `extract` and `draft` send evidence to OpenAI. They require both `--allow-api-upload` and a locally configured `OPENAI_API_KEY`; API usage can incur charges. Set the key through your preferred local secret-management method. Do not paste it into source, JSON, or chat.

Choose an available API model supporting image inputs and structured outputs; no model is silently selected. The model name below is a placeholder. Extraction sends one page image and its text layer per request, checkpoints each completed page, and resumes by skipping extracted pages. Start with one page to assess handwriting quality and cost.

```powershell
$pdrModel = 'YOUR_AVAILABLE_VISION_MODEL'
& $pdrPython pdr_tool.py extract --run 'runs\fall2026-pdr' --page 'PAGE_ID_FROM_INDEX' --model $pdrModel --allow-api-upload
# Omit --page to process all remaining pages.
```

Open the source image and proposed extraction in the index. Correct the relevant page's `extraction` object in `state.json` with a text editor. You can also manually enter extraction without an API; `Extraction` in `pdr_tool.py` is the field contract. A blank mark is `""`; do not replace it with zero. Preserve questions, suggestions, conflicting positions, provisional reviewer names, and uncertain text. Keep comments in stable order after drafting because evidence IDs use page ID and comment index.

Confirm only after a human has checked the page, extraction completeness, literal marks, reviewer attribution, and team identity:

```powershell
& $pdrPython pdr_tool.py review --run 'runs\fall2026-pdr' --page 'PAGE_ID' --team 'CATENA' --by 'Instructor name' --confirm-content-reviewed
# Omit --team for an unidentified sheet: it is reviewed but quarantined.
```

Use the same canonical team name for every mapped page. Team mappings in the pilot can guide inspection but are not automatically adopted. In particular, the unnamed page 20 must not be assigned by adjacency. Review fingerprints are change detection, not authentication or a multi-user approval system.

After verifying a team's pages:

```powershell
& $pdrPython pdr_tool.py draft --run 'runs\fall2026-pdr' --team 'CATENA' --model $pdrModel --allow-api-upload
& $pdrPython pdr_tool.py audit --run 'runs\fall2026-pdr' --draft 'PATH_TO_DRAFT_JSON'
& $pdrPython pdr_tool.py report --run 'runs\fall2026-pdr'
```

Draft JSON and HTML go in the run's `drafts` folder. Partial drafts can be inspected, but the audit stays blocked until all cycle pages have human verification or quarantine. Re-run the audit after changes; saved HTML/audit files are snapshots, not live approval indicators. Exit codes: 0 successful operation/structurally clear audit, 1 blocked audit, 2 input/API failure.

## Instructor evaluation before use

Build a human-adjudicated reference set from the original PDFs, using the pilot as a hypothesis rather than ground truth. Compare both extraction and final drafts. For each run record:

| Measure | How to assess |
| --- | --- |
| Extraction omissions | Reference substantive comments absent from the evidence ledger |
| Unsupported claims | Draft assertions without faithful support in the cited original page |
| Misattributions | Wrong team, reviewer, source type, or page/row |
| Altered meaning | Questions turned into claims, suggestions made mandatory, or presentation gaps treated as absent work |
| Missed safety concerns | Safety comments absent or weakened in the final feedback |
| Disagreement retention | Both incompatible positions retained with attribution |
| Action usefulness | Instructor rates each suggested deliverable on a defined 1–5 scale |

Require zero unsupported claims and zero missed safety concerns in the reviewed release draft. Confirm all substantive comments are represented or traceably consolidated. Structural audits do not measure these semantic acceptance conditions.

Useful regression cases from the pilot: CATENA's incompatible net/enclosure suggestions; Active Textiles' mixed schedule evidence; VITABee's absent versus brief safety coverage; Lumbar Puncture's local timing critique alongside overall praise; unnamed page 20; provisional reviewer spelling; positive boxes beside narrative concerns. Current automated tests use fictional fixtures to check mechanics, not model quality.

## Boundaries and next work

Not yet implemented: editing or deleting existing transcriptions in the browser, semantic cross-source deduplication of concerns, explicit conflict-group/alias adjudication UI, automated semantic evaluation, incremental cross-cycle change summaries, or authenticated approvals. The browser supports adding transcriptions and correcting team assignment; use JSON editing for deeper evidence corrections. Exact duplicate files and identical comment wording are grouped; potentially derived consolidated forms still require human checking. Read-only blank rubric pages still need verification. API calls have no automatic retries; CLI extraction checkpoints completed pages.

The optional adapter follows the official [Responses structured output format](https://developers.openai.com/api/docs/guides/structured-outputs) and [image input format](https://developers.openai.com/api/docs/guides/images-vision), with `store: false`. This setting is not a promise of zero retention under all account policies. The adapter has offline mocked tests; live API extraction, cost, and model quality have not been tested in this session.
