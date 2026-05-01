from langchain_core.documents import Document
from pathlib import Path

ALLOWED_FORMATS= {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".php", ".html", ".css"
}

IGNORE_DIRS = {
    ".git", "node_modules", "venv", "__pycache__",
    "dist", "build", ".next"
}

def load_documents(repo_path:str):
    documents = []
    repo_path = Path(repo_path)

    for file_path in repo_path.rglob("*"):
        if any(part in IGNORE_DIRS for part in file_path.parts):
            continue

        if file_path.suffix not in ALLOWED_FORMATS:
            continue

        try:
            content=file_path.read_text(encoding='utf-8')
        except:
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "file_path": str(file_path),
                    "language": file_path.suffix
                }
            )
        )
    return documents
