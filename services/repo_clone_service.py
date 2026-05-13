from fastapi import HTTPException
from git import Repo
from git.exc import GitCommandError
import hashlib
import re
import shlex
import shutil
from pathlib import Path
from urllib.parse import urlsplit

REPO_DIR = Path("repos")
INVALID_REPO_LINK_MESSAGE = "This is not a valid repository link."


def extract_repo_link(link: str):
    link = link.strip()

    if not link.startswith("git clone "):
        return link

    try:
        parts = shlex.split(link)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid git clone command.")

    options_with_value = {
        "-b",
        "--branch",
        "-c",
        "--config",
        "-j",
        "--jobs",
        "-o",
        "--origin",
        "--depth",
        "--shallow-since",
        "--shallow-exclude",
        "--reference",
        "--reference-if-able",
        "--server-option",
        "--template",
        "-u",
        "--upload-pack",
    }

    index = 2
    while index < len(parts):
        part = parts[index]

        if part in options_with_value:
            index += 2
            continue

        if any(part.startswith(f"{option}=") for option in options_with_value):
            index += 1
            continue

        if part.startswith("-"):
            index += 1
            continue

        return part

    raise HTTPException(status_code=400, detail="Could not find a repository URL in the git clone command.")


def normalize_repo_link(link: str):
    normalized_link = extract_repo_link(link).rstrip("/")

    if normalized_link.endswith(".git"):
        normalized_link = normalized_link[:-4]

    return normalized_link


def repo_id_from_link(link: str):
    return hashlib.sha256(normalize_repo_link(link).encode("utf-8")).hexdigest()[:16]


def is_supported_repo_link(link: str):
    if link.startswith("git@"):
        return True

    parsed_link = urlsplit(link)

    return parsed_link.scheme in {"http", "https", "ssh", "git"} and bool(parsed_link.netloc)


def is_invalid_repo_error(error: GitCommandError):
    message = getattr(error, "stderr", "") or str(error)
    message = message.lower()

    return any(
        phrase in message
        for phrase in [
            "repository not found",
            "not found",
            "could not read from remote repository",
            "does not appear to be a git repository",
            "repository '",
            "authentication failed",
            "access denied"
        ]
    )


def clone_failure_message(error: GitCommandError):
    if is_invalid_repo_error(error):
        return INVALID_REPO_LINK_MESSAGE

    return "Could not clone repository. Please check that the repository link is public and cloneable."


def clone_repo(link:str, force_reindex: bool = False):
    link = extract_repo_link(link)

    if not is_supported_repo_link(link):
        raise HTTPException(status_code=400, detail=INVALID_REPO_LINK_MESSAGE)

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

    try:
        Repo.clone_from(link,full_path, depth=1)
    except GitCommandError as error:
        shutil.rmtree(full_path, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail=clone_failure_message(error)
        )

    return {
        "repo_id" : repo_id,
        "path" : full_path,
        "cached": False
    }
