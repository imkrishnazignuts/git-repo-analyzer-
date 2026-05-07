from langchain_core.documents import Document
from pathlib import Path

ALLOWED_FORMATS= {
    ".py", ".js", ".ts", ".tsx", ".jsx",".dart",
     ".php", ".json", ".md"
}

IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", "coverage", "__MACOSX", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".idea", ".vscode"
}

IGNORE_FILES = {
    ".DS_Store"
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".dart": "dart",
    ".java": "java",
    ".go": "go",
    ".php": "php",
    ".json": "json",
    ".md": "markdown",
}

MAX_FILE_SIZE_BYTES = 300_000


def should_ignore(file_path: Path):
    if file_path.name in IGNORE_FILES:
        return True

    return any(part in IGNORE_DIRS for part in file_path.parts)


def load_documents(repo_path:str):
    documents = []
    repo_path = Path(repo_path)

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue

        if should_ignore(file_path):
            continue

        suffix = file_path.suffix.lower()

        if suffix not in ALLOWED_FORMATS:
            continue

        try:
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue

        try:
            content=file_path.read_text(encoding='utf-8')
        except:
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "file_path": str(file_path.relative_to(repo_path)),
                    "language": LANGUAGE_BY_EXTENSION.get(suffix, suffix.lstrip("."))
                }
            )
        )
    return documents
