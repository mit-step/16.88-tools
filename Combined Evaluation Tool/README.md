# Design Review Suite · 16.88J / MAS.838

One Python application with **PDR**, **CDR**, and **ESDP** tabs across the top. All three tools run on one port, with one production WSGI server. Their existing workflows, rubric definitions, evidence citations, optional AI modes and exports are preserved. Switching tabs retains the current page, unsaved form inputs and ESDP results.

## Upload to GitHub

Create an empty GitHub repository, then upload the **contents of this folder** to its root, including `.gitignore`, `.dockerignore`, and `.env.example`. GitHub Desktop can also add this folder as a local repository and publish it. The application has not been published automatically.

Keep the three tool directories in place: the shared application loads their engines and assets by their existing names. Local reviews, credentials, virtual environments and generated outputs are excluded from this prepared folder. The included `.gitignore` also excludes these files when you develop locally.

## Repository layout

```text
app.py                       Shared application launcher
review_suite/                Unified server, top tabs, RAG/LLM extension interface
PDR Evaluation Tool/         PDR engine and interface assets
CDR Evaluation Tool/         CDR engine, assets and course reference documents
ESDP Evaluation Tool/        ESDP engine, assets and rubric
tests/                      Shared application integration and browser checks
deploy/                      AWS instructions and Nginx example
Dockerfile, compose.yaml     Container deployment
requirements.txt             Python dependencies
.env.example                 Empty configuration template
build_deploy_bundle.py       Source-only deployment ZIP builder
```

## Open locally

Install Python 3.10+ and run these commands from this repository folder on Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

After setup, you can also double-click **Start Review Suite.cmd**. Open **http://127.0.0.1:8080** and keep the server running while you work.

On Linux/macOS, use `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, and `.venv/bin/python app.py`. Optional launch arguments: `--host` and `--port`.

## Existing data and persistence

This repository contains application source and course reference documents only. A fresh checkout starts with empty review workspaces.

If you separately restore legacy data, the first local startup copies each existing `PDR Evaluation Tool/workspace-data` and `CDR Evaluation Tool/workspace-data` into `suite-data/pdr` and `suite-data/cdr`, including sources, images and history. Originals remain untouched. Subsequent launches use the copies; changes in standalone tools are not synchronized. Existing unified folders are never overwritten. Stop the application before copying or restoring data. JSON exports omit original PDFs and images; back up the entire `suite-data` directory.

Set `REVIEW_IMPORT_LEGACY=0` before starting to create empty workspaces. Docker always starts empty, and source deployment archives exclude student reviews and workspace data. ESDP reports remain in the current browser session, as before: export them to keep a copy. Refreshing the application clears the ESDP report.

## Architecture

```text
Browser: top tabs → retained PDR / CDR / ESDP views
                         ↓ one origin
Flask application + Waitress (one process, eight threads)
  /tools/pdr/api/*  → existing PDR engine → persistent PDR workspace
  /tools/cdr/api/*  → existing CDR engine → persistent CDR workspace
  /tools/esdp/api/* → existing ESDP extraction / review engine
  /api/assistant/query → optional provider interface
```

The three tool directories contain the engines and browser assets used by the shared application. Launch the shared application from the repository root. `review_suite/modules.py` loads their engines under distinct module names. The shared server serves their interfaces under separate URL namespaces inside retained frames, so styling and in-tool navigation remain independent. No three-server launcher or browser-side API keys are needed. `review_suite/app.py` owns request limits, origin checks, CSRF tokens, hosted access and error handling.

## AWS deployment

See **deploy/AWS.md** for Docker, EC2/Nginx and ECS guidance. Build a source-only upload archive with:

```powershell
.\.venv\Scripts\python.exe build_deploy_bundle.py
```

The ZIP is written to `dist/design-review-suite.zip` from an explicit allowlist. Deployment credentials, examples, reviews, local data, virtual environments and secrets are excluded. Deployment is not automatic. Build and validate the image on a Docker-enabled host.

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `PORT`, `REVIEW_HOST` | Default `8080`, `127.0.0.1`; container binds `0.0.0.0` |
| `REVIEW_DATA_DIR` | Persistent data root; default `suite-data`, container `/data` |
| `REVIEW_IMPORT_LEGACY` | `1` copies existing local data once; `0` starts empty |
| `REVIEW_PUBLIC_ORIGIN` | Exact HTTPS origin for hosted access, without a path or trailing slash |
| `REVIEW_ACCESS_TOKEN` | Hosted workspace access code, at least 24 characters |
| `REVIEW_TRUST_PROXY` | `1` trusts one proxy for client IP and scheme; default `0` |
| `OPENAI_API_KEY` | Optional server-side key used by the existing AI review adapters |
| `PDR_MODEL`, `CDR_MODEL`, `ESDP_MODEL` | Explicit model names for the respective optional AI modes |
| `REVIEW_ASSISTANT_FACTORY` | Future provider factory, e.g. `my_provider:create_provider` |

Python launchers read process environment variables. Docker Compose reads `.env`; copy `.env.example` and fill it locally. No API/model is selected automatically. AI review still requires the existing explicit upload selection/consent. Hosting requires an HTTPS origin and access code; otherwise only local hostnames are accepted. Hosted access uses a secure, HTTP-only, same-site cookie. The access code is shared workspace access, not individual user accounts or role-based permissions.

## Attach a RAG/LLM provider later

`review_suite/assistant.py` defines a provider-neutral `AssistantProvider.answer(question=..., evidence=...)` interface. Attach a provider with `create_app(assistant=provider)` or a server-side factory named by `REVIEW_ASSISTANT_FACTORY`. Nothing calls an LLM or vector database through this interface until a provider is installed and a request explicitly supplies `consent: true`.

The API accepts `POST /api/assistant/query` with `X-Review-Token` from `/api/config`, and JSON such as:

```json
{"question":"Which concerns still need attention?","tool":"cdr","team":"catena","consent":true}
```

The provider receives only the requested PDR/CDR tool/team evidence: literal comment text, source filename, physical page number, review status, and stable IDs. Return `{"answer":"...", "citations":["cdr:DOCUMENT_SHA:PAGE:COMMENT_INDEX"]}`. Out-of-scope or unknown citations are rejected; citation membership does not establish semantic support. The provider is responsible for embeddings/retrieval/reranking, model configuration, prompt-injection defenses and faithful answers. Keep source text as untrusted evidence and retain instructor review. Draft extractions are included with explicit review status; a provider may restrict retrieval to reviewed evidence.

ESDP text stays ephemeral and is not automatically added to the shared corpus. Persistent student submissions, authorized knowledge-library uploads, document versioning, per-user retrieval permissions and a provider-facing assistant interface can be added at this boundary. There is no enabled chat UI or claimed RAG functionality today.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/browser_check.cjs
```

Start the suite before running the optional browser check. Install its dependencies with `npm install --no-save playwright` and `npx playwright install chromium`. It uses Chromium by default; set `REVIEW_BROWSER_CHANNEL=msedge` to use an installed Edge browser instead. Screenshots go into `test-results`. The Python integration tests use temporary workspaces; the original standalone test suites and their document fixtures are not part of this repository.

## Current operating limits

Use **one process / one container replica** against a data directory. JSON storage has process-local locks and is not designed for multiple writers across instances. The workspace is shared by everyone holding its access code. Individual student accounts, isolated submissions, staff roles, Touchstone/SAML, asynchronous review queues and database transactions are future work. Replace JSON storage with a database and add scoped identity enforcement before a multi-tenant rollout. Optional AI behavior has offline tests; live model quality and provider cost are not validated.
