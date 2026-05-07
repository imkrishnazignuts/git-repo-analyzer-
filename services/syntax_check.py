import ast
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from pydantic import BaseModel
from fastapi import HTTPException,APIRouter
import re

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

class SyntaxCheckRequest(BaseModel):
    repo_id: str
router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", "coverage","__MACOSX"
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",".dart", ".php"
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".php": "php"
}



def clean_error_message(message: str, file_path: Path):
    # remove terminal colors
    message = ANSI_ESCAPE.sub("", message)

    # remove full absolute path
    message = message.replace(str(file_path.absolute()), str(file_path.name))

    # remove repo absolute path if still present
    try:
        repo_root = str(Path.cwd())
        message = message.replace(repo_root, "")
    except:
        pass

    return message.strip()

def read_file_code(file_path: Path):
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def get_relative_path(file_path: Path, repo_path: Path):
    try:
        return str(file_path.relative_to(repo_path))
    except ValueError:
        return str(file_path)


def get_code_snippet(file_path: Path, line=None, context=2):
    code = read_file_code(file_path)

    if not code:
        return ""

    lines = code.splitlines()

    if not line:
        return "\n".join(lines[:10])

    start = max(line - context - 1, 0)
    end = min(line + context, len(lines))

    return "\n".join(
        f"{line_number}: {lines[index]}"
        for index, line_number in enumerate(range(start + 1, end + 1), start)
    )


def make_issue(file_path, repo_path, language, message, line=None, rule="syntax-error", code=None):
    path_obj = Path(file_path)

    clean_message = clean_error_message(message, path_obj)

    return {
        "file_path": get_relative_path(path_obj, repo_path),
        "language": language,
        "line": line,
        "problem": clean_message,
        "rule": rule,
        "code": code if code is not None else get_code_snippet(path_obj, line)
    }


def command_path(command_name: str):
    local_command = Path("node_modules") / ".bin" / command_name

    if local_command.exists():
        return str(local_command)

    return shutil.which(command_name) or command_name


def run_command(command, cwd=None, timeout=30):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip()

        return None

    except FileNotFoundError:
        return f"Checker not installed: {command[0]}"
    except subprocess.TimeoutExpired:
        return "Syntax checker timed out"


def parse_first_line_number(message: str):
    patterns = [
        r":(\d+):\d+:",
        r"\((\d+):\d+\)",
        r"line\s+(\d+)",
        r"Line\s+(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message)

        if match:
            return int(match.group(1))

    return None


def parse_esbuild_problem(message: str):
    match = re.search(r"\[ERROR\]\s*(.+)", message)

    if match:
        return match.group(1).strip()

    return message


def check_python(file_path: Path, repo_path: Path):
    try:
        code = file_path.read_text(encoding="utf-8", errors="ignore")
        ast.parse(code)
        return []
    except SyntaxError as e:
        return [make_issue(file_path, repo_path, "python", e.msg, e.lineno, "python-syntax")]


def check_json(file_path: Path, repo_path: Path):
    try:
        json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
        return []
    except json.JSONDecodeError as e:
        return [make_issue(file_path, repo_path, "json", e.msg, e.lineno, "json-parse")]


def check_esbuild(file_path: Path, repo_path: Path):
    suffix = file_path.suffix.lower()

    loader_map = {
        ".js": "js",
        ".jsx": "jsx",
        ".ts": "ts",
        ".tsx": "tsx",
    }

    loader = loader_map.get(suffix, "js")

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "out.js"

        error = run_command([
            command_path("esbuild"),
            str(file_path),
            "--bundle=false",
            f"--loader:.{loader}={loader}",
            f"--outfile={out_file}",
            "--log-level=error",
            "--color=false"
        ])

    if error:
        line = parse_first_line_number(error)
        language = LANGUAGE_BY_EXTENSION.get(suffix, loader)
        return [make_issue(file_path, repo_path, language, parse_esbuild_problem(error), line, f"{loader}-syntax")]

    return []


def check_java(file_path: Path, repo_path: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        error = run_command(["javac", "-d", tmpdir, str(file_path)])

    if error:
        line = parse_first_line_number(error)
        return [make_issue(file_path, repo_path, "java", error, line, "java-syntax")]

    return []


def check_go(file_path: Path, repo_path: Path):
    error = run_command(["gofmt", "-e", "-d", str(file_path)])

    if error:
        line = parse_first_line_number(error)
        return [make_issue(file_path, repo_path, "go", error, line, "go-syntax")]

    return []


def check_php(file_path: Path, repo_path: Path):
    error = run_command(["php", "-l", str(file_path)])

    if error:
        line = parse_first_line_number(error)
        return [make_issue(file_path, repo_path, "php", error, line, "php-syntax")]

    return []


def check_html(file_path: Path, repo_path: Path):
    error = run_command([
        command_path("htmlhint"),
        "--format",
        "json",
        str(file_path)
    ])

    if error:
        try:
            reports = json.loads(error)
        except json.JSONDecodeError:
            return [make_issue(file_path, repo_path, "html", error, parse_first_line_number(error), "htmlhint")]

        issues = []

        for report in reports:
            for message in report.get("messages", []):
                line = message.get("line")
                rule = message.get("rule", {}).get("id") or "htmlhint"
                issues.append(make_issue(
                    file_path,
                    repo_path,
                    "html",
                    message.get("message", ""),
                    line,
                    rule,
                    message.get("evidence") or get_code_snippet(file_path, line)
                ))

        return issues

    return []


def check_css(file_path: Path, repo_path: Path):
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "stylelint.config.json"
        config_file.write_text('{"rules":{}}', encoding="utf-8")

        error = run_command([
            command_path("stylelint"),
            str(file_path),
            "--config",
            str(config_file),
            "--allow-empty-input",
            "--formatter",
            "json"
        ])

    if error:
        try:
            reports = json.loads(error)
        except json.JSONDecodeError:
            return [make_issue(file_path, repo_path, "css", error, parse_first_line_number(error), "stylelint")]

        issues = []

        for report in reports:
            for warning in report.get("warnings", []):
                line = warning.get("line")
                issues.append(make_issue(
                    file_path,
                    repo_path,
                    "css",
                    warning.get("text", ""),
                    line,
                    warning.get("rule") or "stylelint"
                ))

        return issues

    return []


def check_single_file(file_path: Path, repo_path: Path):
    suffix = file_path.suffix.lower()

    if suffix == ".py":
        return check_python(file_path, repo_path)

    if suffix in [".js", ".jsx", ".ts", ".tsx"]:
        return check_esbuild(file_path, repo_path)

    if suffix == ".java":
        return check_java(file_path, repo_path)

    if suffix == ".go":
        return check_go(file_path, repo_path)

    if suffix == ".php":
        return check_php(file_path, repo_path)

    if suffix == ".json":
        return check_json(file_path, repo_path)

    return []


def check_project_syntax(repo_path: Path):
    issues = []
    checked_files = 0
    skipped_files = 0

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue

        if any(part in IGNORE_DIRS for part in file_path.parts):
            skipped_files += 1
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped_files += 1
            continue

        checked_files += 1

        try:
            issues.extend(check_single_file(file_path, repo_path))
        except Exception as e:
            language = LANGUAGE_BY_EXTENSION.get(file_path.suffix.lower(), "file")
            issues.append(make_issue(
                file_path,
                repo_path,
                language,
                f"Could not check {language} syntax: {str(e)}",
                None,
                "syntax-check-failed"
            ))

    return {
        "checked_files": checked_files,
        "skipped_files": skipped_files,
        "issues": issues
    }

@router.post("/syntax-check")
def syntax_check_project(request: SyntaxCheckRequest):
    repo_path = Path("repos") / request.repo_id

    if not repo_path.exists():
        raise HTTPException(status_code=404, detail="Repository not found")

    result = check_project_syntax(repo_path)

    return {
        "summary": f"Syntax check completed. Checked {result['checked_files']} files and found {len(result['issues'])} syntax issues.",
        "repo_id": request.repo_id,
        "checked_files": result["checked_files"],
        "skipped_files": result["skipped_files"],
        "issues": result["issues"]
    }
