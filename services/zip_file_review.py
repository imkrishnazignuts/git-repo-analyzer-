import shutil
import zipfile
import hashlib
from pathlib import Path

from fastapi import UploadFile, HTTPException, APIRouter, File
from pydantic import BaseModel
from .spiltter import split_document
from .chromadb_setup import create_vectorstore, get_index_metadata, save_index_metadata, vectorstore_exists
from . import read_repo

router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

ZIP_REPO_DIR = Path("repos")

PROJECT_MARKERS = {
    "package.json",
    "composer.json",
    "requirements.txt",
    "pyproject.toml",
    "manage.py",
    "artisan",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "nuxt.config.js",
    "nuxt.config.ts",
    "vue.config.js",
    "nest-cli.json",
}

IGNORE_PROJECT_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", ".nuxt",
    "__MACOSX", "__pycache__", ".venv", "venv", "coverage", ".cache"
}


class ZipProjectIndexRequest(BaseModel):
    zip_id: str
    project_path: str


def safe_extract_zip(zip_ref: zipfile.ZipFile, extract_path: Path):
    extract_root = extract_path.resolve()

    for member in zip_ref.infolist():
        target_path = (extract_path / member.filename).resolve()

        try:
            target_path.relative_to(extract_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ZIP file path")

    zip_ref.extractall(extract_path)


def relative_project_path(project_path: Path, extract_path: Path):
    relative_path = project_path.relative_to(extract_path).as_posix()
    return "" if relative_path == "." else relative_path


def detect_project_roots(extract_path: Path):
    candidates = []

    for directory in [extract_path, *[path for path in extract_path.rglob("*") if path.is_dir()]]:
        if any(part in IGNORE_PROJECT_DIRS for part in directory.parts):
            continue

        markers = sorted(
            child.name
            for child in directory.iterdir()
            if child.is_file() and child.name in PROJECT_MARKERS
        )

        if markers:
            candidates.append({
                "name": directory.name if directory != extract_path else extract_path.name,
                "path": relative_project_path(directory, extract_path),
                "absolute_path": directory,
                "markers": markers
            })

    if not candidates:
        children = [
            item for item in extract_path.iterdir()
            if item.name not in IGNORE_PROJECT_DIRS
        ]

        if len(children) == 1 and children[0].is_dir():
            return [{
                "name": children[0].name,
                "path": children[0].relative_to(extract_path).as_posix(),
                "absolute_path": children[0],
                "markers": []
            }]

        return [{
            "name": extract_path.name,
            "path": "",
            "absolute_path": extract_path,
            "markers": []
        }]

    if len(candidates) == 1 and candidates[0]["absolute_path"] == extract_path:
        children = [
            item for item in extract_path.iterdir()
            if item.name not in IGNORE_PROJECT_DIRS
        ]

        if len(children) == 1 and children[0].is_dir():
            nested_markers = sorted(
                child.name
                for child in children[0].iterdir()
                if child.is_file() and child.name in PROJECT_MARKERS
            )

            if nested_markers:
                return [{
                    "name": children[0].name,
                    "path": children[0].relative_to(extract_path).as_posix(),
                    "absolute_path": children[0],
                    "markers": nested_markers
                }]

    return candidates


def public_project(project, zip_id: str):
    project_path = project["path"]
    project_hash = hashlib.sha256(f"{zip_id}:{project_path}".encode("utf-8")).hexdigest()[:16]

    return {
        "name": project["name"],
        "path": project_path,
        "repo_id": project_hash,
        "markers": project["markers"]
    }


def index_project_path(repo_id: str, project_path: Path, cached: bool = False):
    metadata = get_index_metadata(repo_id)

    if cached and vectorstore_exists(repo_id) and metadata:
        if not metadata.get("source_path"):
            save_index_metadata(
                repo_id,
                metadata.get("files_loaded", 0),
                metadata.get("chunks_created", 0),
                str(project_path)
            )

        return {
            "message": "ZIP project indexed successfully",
            "repo_id": repo_id,
            "cached": True,
            "files_loaded": metadata.get("files_loaded", 0),
            "chunks_created": metadata.get("chunks_created", 0)
        }

    documents = read_repo.load_documents(project_path)
    chunks = split_document(documents)
    create_vectorstore(chunks, repo_id)
    save_index_metadata(repo_id, len(documents), len(chunks), str(project_path))

    return {
        "message": "ZIP project indexed successfully",
        "repo_id": repo_id,
        "cached": cached,
        "files_loaded": len(documents),
        "chunks_created": len(chunks),
        "file_filter": dict(read_repo.LAST_LOAD_STATS)
    }


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
            "zip_id": repo_id,
            "path": extract_path,
            "cached": True
        }

    extract_path.mkdir(parents=True, exist_ok=True)

    zip_path.write_bytes(zip_bytes)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            safe_extract_zip(zip_ref, extract_path)
    except zipfile.BadZipFile:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_path, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid zip file")

    zip_path.unlink(missing_ok=True)

    return {
        "repo_id": repo_id,
        "zip_id": repo_id,
        "path": extract_path,
        "cached": False
    }

@router.post("/index-zip")
def index_zip_project(file: UploadFile = File(...)):
    repo = extract_zip_project(file)
    projects = detect_project_roots(repo["path"])
    public_projects = [public_project(project, repo["zip_id"]) for project in projects]

    if len(public_projects) > 1:
        return {
            "message": "Multiple projects detected in ZIP. Choose one project to index and review.",
            "multiple": True,
            "zip_id": repo["zip_id"],
            "projects": public_projects
        }

    project = projects[0]
    public = public_projects[0]
    result = index_project_path(public["repo_id"], project["absolute_path"], repo.get("cached", False))
    result["multiple"] = False
    result["zip_id"] = repo["zip_id"]
    result["project"] = public

    return result


@router.post("/index-zip-project")
def index_selected_zip_project(request: ZipProjectIndexRequest):
    extract_path = ZIP_REPO_DIR / request.zip_id

    if not extract_path.exists():
        raise HTTPException(status_code=404, detail="ZIP upload not found")

    requested_path = Path(request.project_path)

    if requested_path.is_absolute() or ".." in requested_path.parts:
        raise HTTPException(status_code=400, detail="Invalid project path")

    project_path = (extract_path / requested_path).resolve()

    if not str(project_path).startswith(str(extract_path.resolve())) or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not found in ZIP")

    projects = detect_project_roots(extract_path)
    matched_project = next(
        (project for project in projects if project["path"] == request.project_path),
        None
    )

    if not matched_project:
        raise HTTPException(status_code=400, detail="Selected path is not a detected project")

    public = public_project(matched_project, request.zip_id)
    result = index_project_path(public["repo_id"], matched_project["absolute_path"], True)
    result["multiple"] = False
    result["zip_id"] = request.zip_id
    result["project"] = public

    return result
