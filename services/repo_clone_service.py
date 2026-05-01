from git import Repo
from fastapi import APIRouter
from uuid import uuid4
from pathlib import Path

REPO_DIR = Path("repos")

def clone_repo(link:str):
    repo_id = str(uuid4())
    full_path = REPO_DIR / repo_id
    full_path.mkdir(parents=True,exist_ok=True)

    Repo.clone_from(link,full_path)

    return {
        "repo_id" : repo_id,
        "path" : full_path
    }
