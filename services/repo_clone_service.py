from git import Repo
import hashlib
import shutil
from pathlib import Path

REPO_DIR = Path("repos")

def repo_id_from_link(link: str):
    return hashlib.sha256(link.strip().encode("utf-8")).hexdigest()[:16]


def clone_repo(link:str, force_reindex: bool = False):
    repo_id = repo_id_from_link(link)
    full_path = REPO_DIR / repo_id

    if force_reindex and full_path.exists():
        shutil.rmtree(full_path)

    if full_path.exists() and any(full_path.iterdir()):
        return {
            "repo_id" : repo_id,
            "path" : full_path,
            "cached": True
        }

    full_path.mkdir(parents=True,exist_ok=True)

    Repo.clone_from(link,full_path, depth=1)

    return {
        "repo_id" : repo_id,
        "path" : full_path,
        "cached": False
    }
