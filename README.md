# Git Repo Analyzer

Git Repo Analyzer is a FastAPI web app that clones a GitHub repository, reads source files, stores code chunks in ChromaDB, and uses an AI model to answer code review questions.

## Features

- Clone a GitHub repository from a URL
- Load supported source files from the cloned repo
- Split code into chunks for retrieval
- Store embeddings in ChromaDB
- Ask AI-powered questions about bugs, security issues, runtime errors, performance, and improvements
- View structured review results in a browser UI

## Tech Stack

- Python
- FastAPI
- LangChain
- ChromaDB
- Hugging Face embeddings
- Groq LLM
- HTML, CSS, and JavaScript

## Folder Structure

```text
.
├── main.py
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── services/
│   ├── chromadb_setup.py
│   ├── read_repo.py
│   ├── repo_clone_service.py
│   ├── review_code.py
│   └── spiltter.py
└── .gitignore
```

## Supported File Types

The analyzer currently reads:

```text
.py, .js, .ts, .tsx, .jsx, .java, .go, .php, .html, .css
```

It ignores folders such as:

```text
.git, node_modules, venv, __pycache__, dist, build, .next
```

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required packages:

```bash
pip install fastapi uvicorn python-dotenv gitpython langchain-core langchain-groq langchain-chroma langchain-huggingface langchain-text-splitters sentence-transformers
```

Create a `.env` file in the project root:

```text
GROQ_API_KEY=your_groq_api_key_here
```

## Run Locally

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

Open the app:

```text
http://127.0.0.1:8000
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

## API Endpoints

### Index a Repository

```http
POST /ai/index
```

Request body:

```json
{
  "repo_link": "https://github.com/user/repo"
}
```

### Ask a Review Question

```http
POST /ai/ask
```

Request body:

```json
{
  "repo_id": "generated_repo_id",
  "question": "Find bugs and security issues in this repository."
}
```

## Important Notes

- Do not upload `.env` to GitHub.
- Do not upload `venv/`, `repos/`, `chromadb/`, or `__pycache__/`.
- Local repository clones are saved inside `repos/`.
- ChromaDB vector data is saved inside `chromadb/`.
- If an API key was ever exposed publicly, rotate it before deploying or sharing the project.

