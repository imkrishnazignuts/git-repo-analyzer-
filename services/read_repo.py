from langchain_core.documents import Document
from pathlib import Path

CODE_FORMATS = {
    ".py", ".php", ".js", ".jsx", ".ts", ".tsx", ".vue", ".html", ".htm"
}

STYLE_FORMATS = {
    ".css", ".scss", ".sass", ".less"
}

CONFIG_FORMATS = {
    ".json", ".toml", ".yaml", ".yml", ".ini", ".env", ".md"
}

ALLOWED_FORMATS = CODE_FORMATS | CONFIG_FORMATS

IMPORTANT_CONFIG_FILES = {
    "package.json",
    "composer.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
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
    "tailwind.config.js",
    "tailwind.config.ts",
    "postcss.config.js",
    "tsconfig.json",
    "jsconfig.json",
    "nest-cli.json",
    ".env.example",
}

IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", "coverage", "__MACOSX", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".idea", ".vscode", "vendor",
    "storage", "bootstrap/cache", "public/build", "public/vendor",
    ".nuxt", ".output", ".angular", ".turbo", ".cache", "target"
}

IGNORE_FILES = {
    ".DS_Store", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "poetry.lock", "Pipfile.lock", "npm-shrinkwrap.json"
}

GENERATED_FILE_PATTERNS = {
    ".min.js", ".min.css", ".bundle.js", ".bundle.css", ".map",
    ".d.ts"
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".php": "php",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ini": "ini",
    ".env": "env",
    ".md": "markdown",
}

LANGUAGE_BY_FILENAME = {
    ".env.example": "env",
    "requirements.txt": "python-requirements",
    "package.json": "node-package",
    "composer.json": "php-composer",
    "pyproject.toml": "python-config",
    "setup.py": "python",
    "setup.cfg": "python-config",
    "manage.py": "python",
    "artisan": "php",
    "tsconfig.json": "typescript-config",
    "jsconfig.json": "javascript-config",
    "nest-cli.json": "nestjs-config",
}

MAX_FILE_SIZE_BYTES = 300_000
LAST_LOAD_STATS = {}


def should_ignore(file_path: Path):
    if file_path.name in IGNORE_FILES:
        return True

    if any(file_path.name.endswith(pattern) for pattern in GENERATED_FILE_PATTERNS):
        return True

    path_text = file_path.as_posix()
    normalized_parts = set(file_path.parts)

    return any(
        ignore_dir in normalized_parts or f"/{ignore_dir}/" in f"/{path_text}/"
        for ignore_dir in IGNORE_DIRS
    )


def is_important_config(file_path: Path):
    return file_path.name in IMPORTANT_CONFIG_FILES


def should_load_file(file_path: Path):
    suffix = file_path.suffix.lower()

    if suffix in CODE_FORMATS:
        return True

    if suffix in CONFIG_FORMATS:
        return is_important_config(file_path)

    if file_path.name in IMPORTANT_CONFIG_FILES:
        return True

    return False


def language_for_file(file_path: Path):
    if file_path.name in LANGUAGE_BY_FILENAME:
        return LANGUAGE_BY_FILENAME[file_path.name]

    return LANGUAGE_BY_EXTENSION.get(file_path.suffix.lower(), "config")


def load_documents(repo_path:str):
    documents = []
    repo_path = Path(repo_path)
    stats = {
        "loaded": 0,
        "ignored": 0,
        "style_skipped": 0,
        "unsupported": 0,
        "too_large": 0,
        "unreadable": 0
    }

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()

        if should_ignore(file_path):
            stats["ignored"] += 1
            continue

        if suffix in STYLE_FORMATS:
            stats["style_skipped"] += 1
            continue

        if not should_load_file(file_path):
            stats["unsupported"] += 1
            continue

        try:
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                stats["too_large"] += 1
                continue
        except OSError:
            stats["unreadable"] += 1
            continue

        try:
            content=file_path.read_text(encoding='utf-8')
        except:
            stats["unreadable"] += 1
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "file_path": str(file_path.relative_to(repo_path)),
                    "language": language_for_file(file_path)
                }
            )
        )

    stats["loaded"] = len(documents)
    LAST_LOAD_STATS.clear()
    LAST_LOAD_STATS.update(stats)

    return documents
