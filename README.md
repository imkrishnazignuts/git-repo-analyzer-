# Git Repo Analyzer

Git Repo Analyzer is a FastAPI web app that indexes Git repositories or ZIP projects, stores code chunks in ChromaDB, and uses a Groq LLM through LangChain to answer repository questions and run AI-assisted code reviews.

It also includes deterministic syntax checks for selected languages and a browser UI for indexing, asking questions, running full review, and viewing structured findings.

## Features

- Clone and index a public Git repository.
- Upload and index a ZIP project.
- Cache cloned repositories and ChromaDB indexes.
- Force reindex from the UI when you want a fresh clone/vector index.
- Read supported project files and skip dependency/build/cache folders.
- Split files into overlapping chunks for retrieval.
- Store embeddings in persistent ChromaDB folders.
- Ask focused questions about the indexed codebase.
- Run full-project AI review with streamed LLM output in the UI.
- Run deterministic syntax checks for supported languages.
- Configure the Groq model from `.env` using `LLM_MODEL`.
- Run locally or with Docker.

## Tech Stack

- Python 3.11
- FastAPI
- Uvicorn
- LangChain
- Groq LLM
- ChromaDB
- Hugging Face sentence-transformer embeddings
- GitPython
- HTML, CSS, JavaScript
- esbuild for JS/TS syntax checking
- PHP CLI for PHP syntax checking

## Project Structure

```text
.
├── main.py
├── delete.py
├── requirements.txt
├── package.json
├── package-lock.json
├── Dockerfile
├── docker-compose.yml
├── DEPLOY_EC2.md
├── info.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── services/
    ├── chromadb_setup.py
    ├── full_review_code.py
    ├── read_repo.py
    ├── repo_clone_service.py
    ├── review_code.py
    ├── spiltter.py
    ├── syntax_check.py
    └── zip_file_review.py
```

Runtime data is stored in:

```text
repos/
chromadb/
```

## Supported Files

Files currently read and indexed for AI review:

```text
.py, .js, .ts, .tsx, .jsx, .dart, .php, .json, .md
```

HTML and CSS are intentionally not indexed.

Ignored folders include:

```text
.git, node_modules, venv, .venv, __pycache__, dist, build, .next, coverage,
.pytest_cache, .mypy_cache, .ruff_cache, .idea, .vscode
```

Files larger than `300_000` bytes are skipped.

## Syntax Checks

The syntax-check endpoint currently scans:

```text
.py, .js, .jsx, .ts, .tsx, .dart, .php
```

Current checker behavior:

- Python uses `ast.parse`.
- JS/JSX/TS/TSX uses `esbuild`.
- PHP uses `php -l`.
- Dart is currently listed but has no dedicated checker branch, so it does not report Dart syntax errors yet.
- Java, Go, HTML, CSS, and JSON checker helpers exist in code but are not active in the current `SUPPORTED_EXTENSIONS` list.

For local PHP syntax checking, PHP must be installed:

```bash
php -v
```

On macOS:

```bash
brew install php
```

For local JS/TS syntax checking, install Node dependencies:

```bash
npm ci
```

## Environment Variables

Create `.env` in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
LLM_MODEL=llama-3.3-70b-versatile
FULL_REVIEW_WORKERS=2
# Optional:
# HF_TOKEN=your_huggingface_token_here
```

Notes:

- `GROQ_API_KEY` is required.
- `LLM_MODEL` controls the Groq model used by normal ask mode and full review.
- `FULL_REVIEW_WORKERS` currently defaults to `2`.
- Restart the FastAPI server after changing `.env`.

## Local Setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install Node dependencies for local JS/TS syntax checks:

```bash
npm ci
```

Create `.env`:

```bash
cp .env.example .env
```

Edit `.env` and add your real keys/model settings.

## Run Locally

Start the app:

```bash
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

## Cleanup Script

`delete.py` deletes and recreates `repos/` and `chromadb/` every 30 minutes.

Run in a second terminal:

```bash
python3 delete.py
```

Run in the background:

```bash
nohup python3 delete.py > cleanup.log 2>&1 &
```

Stop it:

```bash
pkill -f delete.py
```

Be careful: this removes all cached repositories and vector indexes.

## Docker

Build and run with Docker Compose:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

The Docker image installs:

- Python dependencies from `requirements.txt`
- Node dependencies from `package-lock.json`
- `git`
- `curl`
- `nodejs`
- `npm`
- `openjdk-17-jdk-headless`
- `golang-go`
- `php-cli`

Docker Compose mounts these folders for persistence:

```text
./repos:/app/repos
./chromadb:/app/chromadb
```

For EC2 deployment, see:

```text
DEPLOY_EC2.md
```

## API Endpoints

### Index Git Repository

```http
POST /ai/index
```

Request:

```json
{
  "repo_link": "https://github.com/user/repo",
  "force_reindex": false
}
```

Response includes:

```json
{
  "message": "Repository indexed successfully",
  "repo_id": "generated_repo_id",
  "cached": false,
  "files_loaded": 10,
  "chunks_created": 25
}
```

### Index ZIP Project

```http
POST /ai/index-zip
```

Request:

- Multipart form upload
- Field name: `file`
- File type: `.zip`

### Ask Repository Question

```http
POST /ai/ask
```

Request:

```json
{
  "repo_id": "generated_repo_id",
  "question": "Where is authentication implemented?"
}
```

This uses Chroma retrieval with `k=5`, builds context from matching chunks, and returns structured JSON.

### Full Project Review

```http
POST /ai/full-review
```

Request:

```json
{
  "repo_id": "generated_repo_id",
  "question": "Review this project for bugs, syntax errors, security issues, runtime errors, and bad practices.",
  "max_workers": 2
}
```

Response:

- Streaming response
- Media type: `application/x-ndjson`
- The frontend reads streamed events and renders live LLM output token by token.

Important detail:

Full review sends only the first `12_000` characters of each file to the LLM:

```python
doc.page_content
```

### Syntax Check

```http
POST /ai/syntax-check
```

Request:

```json
{
  "repo_id": "generated_repo_id"
}
```

Response includes:

```json
{
  "summary": "Syntax check completed...",
  "repo_id": "generated_repo_id",
  "checked_files": 10,
  "skipped_files": 3,
  "issues": []
}
```

## Core Backend Flow

Indexing flow:

1. User submits a Git URL or ZIP file.
2. Backend clones/extracts into `repos/{repo_id}`.
3. `read_repo.py` loads supported files.
4. `spiltter.py` splits documents into chunks.
5. `chromadb_setup.py` embeds and stores chunks.
6. Metadata is saved in `chromadb/{repo_id}/index_metadata.json`.

Ask flow:

1. User asks a question.
2. Chroma retrieves relevant chunks.
3. Prompt sends context and question to Groq.
4. JSON response is rendered in the UI.

Full-review streaming flow:

1. User starts full review.
2. Frontend calls `/ai/full-review`.
3. Backend streams LLM output per file using `chain.stream(...)`.
4. Frontend displays live generated tokens in a card.
5. Completed file output is parsed into structured issues.
6. Syntax checks run after LLM streaming.
7. Final summary is displayed.

## Useful Commands

Check Python files:

```bash
python3 -m py_compile main.py services/*.py delete.py
```

Check frontend JavaScript:

```bash
node --check frontend/app.js
```

View Docker logs:

```bash
docker logs -f git-repo-analyzer
```

Rebuild Docker image:

```bash
docker compose up --build
```

## Security Notes

- Never commit `.env`.
- Rotate any API key that was exposed publicly.
- Public deployments should be protected with HTTPS and access control.
- The app clones repositories and extracts ZIP files, so run it in an isolated environment.
- Keep `repos/` and `chromadb/` out of Git.

