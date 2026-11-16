# ESDP Review

Local application for students to upload an Experiment Safety Data Package and receive a rubric-shaped report. It follows the existing PDR tool's Python/browser setup. The proposed rubric is grounded in the supplied 2023-01 Word template, with alternate-format headings from the Orchid example. The examples are not instructor-adjudicated answers.

## Open the application

Double-click **Start ESDP Review.cmd**, leave its window open, then visit **http://127.0.0.1:8766**. On this computer the launcher uses bundled Python. Elsewhere, install Python 3.10+ and run:

```powershell
py -3 -m pip install -r requirements.txt
py -3 app.py
```

Use `--port 8767` if the default port is occupied. The PDR tool uses 8765, so both can run at once.

## Two review modes

- **Local section inventory** works immediately without a key or external service. It locates possible coverage using section aliases and displays source excerpts, expected content and inspection actions in 12 rubric rows. It does not infer substantive completeness from headings or keywords and produces no quality ratings.
- **AI content review** evaluates readable text against the rubric, produces completeness labels and 0-3 quality ratings, identifies gaps, cites exact source quotes and proposes revisions. It requires an instructor-configured API key and model. This is provisional educational feedback, not a final grade or safety approval.

Upload PDF or DOCX, maximum 20 MB. PDFs support up to 100 pages. The readable-text limit is 160,000 characters; over-limit input is rejected rather than truncated. PDF citations use physical file page numbers. DOCX citations use body paragraph/table positions, preserving body order, since Word pagination is not available. Inspect extracted source text from the report. Export JSON or use Print / save PDF to retain results. Browser refresh discards results.

## Enable AI review

Set `OPENAI_API_KEY` and `ESDP_MODEL` in the server's environment using your local secret-management practice, then restart. Choose a model available to your account that supports the Responses API and strict structured outputs. No model is silently selected. The key stays on the server and is never sent to the browser or included in exports. Do not place keys in source files or chat.

The student explicitly selects AI review and confirms the upload disclosure. Only then does the server send extracted document text, including any personal details it contains, along with the rubric to OpenAI. It does not send raw files, images or the other supplied examples. The request uses `store: false`; this is not a guarantee of zero retention under every account policy. API usage can incur charges.

The adapter follows the official [Responses structured outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). All 12 criteria must appear exactly once. Ratings and completeness must agree; substantive assessments require evidence, and cited quotes must occur in the indicated source block. Invalid, refused or incomplete AI output is rejected. A failed AI call does not silently become a content review. Requests time out after 180 seconds and are not automatically retried. Only one review runs at a time. Quote validation checks source occurrence, not semantic support: an instructor must check that feedback follows from the evidence.

## Proposed rubric

Edit `rubric.json` and restart to change criteria, anchors, expectations, aliases or weights. The 12 criteria cover identity/revisions, objectives, systems, products, interfaces, electrical/batteries, structure, procedures, external failures, hazard analysis, requirements/exemptions, and references/consistency. The weights sum to 100; they are proposed course weights, not official Novespace scoring.

Completeness labels are Complete, Partial, Missing, Not applicable and Not assessable. Quality anchors are 0 (no substantive evidence), 1 (major gaps), 2 (substantive coverage with specific gaps), and 3 (clear, specific and consistent). Reasoned N/A criteria are excluded from the weighted draft indicator. Any Not assessable row withholds the overall indicator. Otherwise the indicator is `100 × sum(weight × score / 3) / sum(assessed weights)`. It does not represent a course grade or flight readiness. Missing means not found in readable submission text, not proof that engineering work was not performed.

## Boundaries before student rollout

This is a single-user local prototype, not a deployed student service. It binds only to loopback, checks local hostnames and same-origin requests, and requires a per-process request token. Do not expose Python's development HTTP server publicly. It stores no documents or reports automatically, although exported JSON includes the extracted text. The provided examples and temporary extraction files remain in this workspace.

OCR, visual diagram review, formulas embedded in images, external attachment verification, authenticated users, submission history and instructor approval/edit workflows are not implemented. For text with missing/scanned PDF pages, AI review is blocked and the local inventory displays limitations. Text-only review cannot establish actual mechanical/electrical compliance or validate scientific/safety claims. References REF-01 through REF-08 were not supplied as standards and are not fetched or assumed current.

The Word template contains guidance, examples and some experiment-specific entries. These are not automatically considered completed student work. The AI prompt treats all document content as untrusted evidence and rejects document instructions that try to change the rubric or review policy. Prompting is a mitigation, not a demonstrated guarantee against prompt injection.

Before course use, have instructors approve the rubric and independently evaluate both examples plus incomplete submissions. Compare omissions, unsupported feedback, misread N/A, retained template text, inconsistent configurations and missed safety concerns. Review quality has not been calibrated or benchmarked. No live AI request was made during implementation; only the API protocol and validation behavior were tested with mocked responses.

Shared hosting can follow the existing PDR/AWS direction, but requires a production serving layer, authentication, per-student isolation, upload/resource limits, rate limits and an agreed retention policy. This Python server cannot be published unchanged to the Sites Cloudflare Worker runtime; no hosting deployment has been performed.

## Validation

```powershell
py -3 -m unittest -v
```

Thirteen tests cover all supplied example files, Word table order, scan handling, input rejection, ratings, exact citations, criterion coverage, weighted indicators, mocked Responses requests, HTTP upload and same-origin protections. Browser QA covers the application and a Skinsuit PDF inventory. These checks establish mechanics, not educational or safety-review accuracy.
