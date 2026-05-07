import shutil
import zipfile
import hashlib
from pathlib import Path

from fastapi import UploadFile, HTTPException,APIRouter,File
from .spiltter import split_document
from .chromadb_setup import create_vectorstore, get_index_metadata, save_index_metadata, vectorstore_exists
from .read_repo import load_documents

router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

ZIP_REPO_DIR = Path("repos")


def extract_zip_project(file: UploadFile):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    zip_bytes = file.file.read()
    repo_id = hashlib.sha256(zip_bytes).hexdigest()[:16]
    extract_path = ZIP_REPO_DIR / repo_id
    zip_path = ZIP_REPO_DIR / f"{repo_id}.zip"

    if extract_path.exists() and any(extract_path.iterdir()):
        return {
            "repo_id": repo_id,
            "path": extract_path,
            "cached": True
        }

    extract_path.mkdir(parents=True, exist_ok=True)

    zip_path.write_bytes(zip_bytes)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_path, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid zip file")

    zip_path.unlink(missing_ok=True)

    return {
        "repo_id": repo_id,
        "path": extract_path,
        "cached": False
    }

@router.post("/index-zip")
def index_zip_project(file: UploadFile = File(...)):
    repo = extract_zip_project(file)

    metadata = get_index_metadata(repo["repo_id"])

    if repo.get("cached") and vectorstore_exists(repo["repo_id"]) and metadata:
        return {
            "message": "ZIP project indexed successfully",
            "repo_id": repo["repo_id"],
            "cached": True,
            "files_loaded": metadata.get("files_loaded", 0),
            "chunks_created": metadata.get("chunks_created", 0)
        }

    documents = load_documents(repo["path"])
    chunks = split_document(documents)
    create_vectorstore(chunks, repo["repo_id"])
    save_index_metadata(repo["repo_id"], len(documents), len(chunks))

    return {
        "message": "ZIP project indexed successfully",
        "repo_id": repo["repo_id"],
        "cached": repo.get("cached", False),
        "files_loaded": len(documents),
        "chunks_created": len(chunks)
    }
