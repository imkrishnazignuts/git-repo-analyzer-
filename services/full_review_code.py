import json
import math
import os
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel
from services import read_repo
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from .chromadb_setup import get_repo_source_path
from .review_code import LLM_MODEL
from .syntax_check import check_project_syntax
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

class FullReviewRequest(BaseModel):
    repo_id: str
    question: str = "Review this project for confirmed major bugs, security vulnerabilities, runtime errors, syntax errors, and bad practices."
    max_workers: int = 1


full_review_llm = ChatGroq(
    model=LLM_MODEL,
    temperature=0
)


full_review_prompt = ChatPromptTemplate.from_template("""
You are a deterministic senior software engineer and security-focused code reviewer.

Review the given file carefully and only report confirmed, actionable defects.

Supported target stacks:
- Python: Django, FastAPI
- PHP: Laravel, Core PHP
- JavaScript/TypeScript: React, Next.js, Vue, Nuxt, Node.js, Express.js, NestJS
- HTML/CSS/JavaScript: Tailwind, Bootstrap, browser JavaScript

Consistency and noise-control rules:
- Return the same findings for the same input across repeated runs.
- Report only defects directly supported by the code shown in this file.
- Do not report speculative issues, style preferences, missing tests, missing docs, generic "add validation" advice, or broad best-practice suggestions.
- Do not report CSS/font/layout/style-only issues unless they cause a definite broken build, security issue, or runtime bug.
- Do not report lockfile, vendor, dependency, generated asset, minified asset, or framework cache issues.
- Do not report an issue if the code is valid in a common framework/library pattern.
- Prefer zero findings over uncertain findings.
- Return every confirmed high or medium severity issue in this file.
- Do not stop at a fixed number of findings when more confirmed issues exist.
- Use severity "high" only for build-breaking, security-critical, data-loss, auth bypass, or definite runtime-crash issues.
- Use severity "medium" for definite functional bugs, definite bad practices with runtime/security impact, or maintainability issues that can cause production defects.
- Use severity "low" only when the user explicitly asks for minor improvements.
- Every issue must include a concrete evidence snippet or symbol from the code.
- Set vulnerability to true only for security issues; otherwise false.

User request:
{question}

File path:
{file_path}

Code:
{code}

Return ONLY valid JSON in this format:

{{
  "issues": [
    {{
      "file_path": "{file_path}",
      "module": "top-level folder, package, or service name; use root for top-level files",
      "issue_type": "bug | syntax_error | security | runtime_error | bad_practice | performance | improvement",
      "severity": "low | medium | high",
      "confidence": "medium | high",
      "vulnerability": false,
      "problem": "",
      "why_it_is_problem": "",
      "evidence": "specific function, line clue, import, config key, or code snippet proving the issue",
      "suggestion": "",
      "improved_code": {{
        "language": "",
        "code": ""
      }}
    }}
  ]
}}

If no issue found, return:  

{{
  "issues": []
}}
"""
)

def review_single_file(doc, question: str):
    wait_for_token_budget(doc.page_content, question)
    chain = full_review_prompt | full_review_llm

    response = chain.invoke({
        "question": question,
        "file_path": doc.metadata.get("file_path", ""),
        "code": doc.page_content
    })

    return parse_llm_json(response)


def estimate_tokens(text: str):
    return max(1, math.ceil(len(text or "") / 4))


def wait_for_token_budget(code: str, question: str):
    tokens_per_minute = int(os.getenv("GROQ_TOKENS_PER_MINUTE", "30000"))
    min_wait_seconds = float(os.getenv("FULL_REVIEW_MIN_WAIT_SECONDS", "0"))

    estimated_tokens = estimate_tokens(code) + estimate_tokens(question) + 1500
    wait_seconds = max(min_wait_seconds, (estimated_tokens / max(tokens_per_minute, 1)) * 60)
    max_wait_seconds = float(os.getenv("FULL_REVIEW_MAX_WAIT_SECONDS", "90"))

    time.sleep(min(wait_seconds, max_wait_seconds))


def is_rate_limit_error(error: Exception):
    message = str(error).lower()

    return any(
        phrase in message
        for phrase in [
            "rate limit",
            "rate_limit",
            "tokens per minute",
            "tpm",
            "too many requests",
            "429"
        ]
    )


def parse_llm_json(response):
    content = getattr(response, "content", response)
    text = str(content).strip()

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = extract_json_object(text)
    text = escape_control_chars_in_json_strings(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some models escape characters that JSON does not require, e.g. "\$".
        repaired_text = re.sub(r'\\(?!["\\/bfnrtu])', "", text)
        return json.loads(repaired_text)


def extract_json_object(text: str):
    start = text.find("{")

    if start == -1:
        raise ValueError("No JSON object found in model response")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                return text[start:index + 1]

    raise ValueError("Incomplete JSON object in model response")


def escape_control_chars_in_json_strings(text: str):
    result = []
    in_string = False
    escaped = False

    for char in text:
        if escaped:
            result.append(char)
            escaped = False
            continue

        if char == "\\":
            result.append(char)
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            result.append(char)
            continue

        if in_string and char == "\n":
            result.append("\\n")
            continue

        if in_string and char == "\r":
            result.append("\\r")
            continue

        if in_string and char == "\t":
            result.append("\\t")
            continue

        result.append(char)

    return "".join(result)


def syntax_issue_to_review_issue(issue):
    return {
        "file_path": issue.get("file_path", ""),
        "module": module_name_from_path(issue.get("file_path", "")),
        "issue_type": "syntax_error",
        "severity": "high",
        "confidence": "high",
        "vulnerability": False,
        "problem": issue.get("problem", ""),
        "why_it_is_problem": f"{issue.get('language', 'Code')} syntax errors can break builds or runtime execution.",
        "evidence": issue.get("code", "") or issue.get("problem", ""),
        "suggestion": f"Fix the {issue.get('rule', 'syntax')} issue on line {issue.get('line')}.",
        "improved_code": {
            "language": issue.get("language", ""),
            "code": issue.get("code", "")
        }
    }


def module_name_from_path(file_path: str):
    parts = [part for part in str(file_path).split("/") if part]
    return parts[0] if len(parts) > 1 else "root"


def as_boolean(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}

    return bool(value)


def normalize_review_issue(issue):
    file_path = issue.get("file_path", "")
    issue["file_path"] = file_path
    issue["module"] = issue.get("module") or module_name_from_path(file_path)
    issue["severity"] = str(issue.get("severity", "medium")).lower()
    issue["issue_type"] = issue.get("issue_type") or "bug"
    issue["confidence"] = str(issue.get("confidence", "medium")).lower()
    issue["vulnerability"] = as_boolean(issue.get("vulnerability")) or issue["issue_type"] == "security"
    issue["evidence"] = issue.get("evidence", "")

    return issue


def normalize_review_issues(issues):
    return [
        normalize_review_issue(issue)
        for issue in issues
        if isinstance(issue, dict)
    ]


def detect_tech_stack(documents):
    language_counts = {}
    config_counts = {}
    frameworks = set()
    config_languages = {
        "env", "python-requirements", "node-package", "php-composer",
        "python-config", "typescript-config", "javascript-config", "nestjs-config",
        "json", "toml", "yaml", "ini", "markdown", "config"
    }

    for doc in documents:
        language = doc.metadata.get("language", "unknown")
        if language in config_languages:
            config_counts[language] = config_counts.get(language, 0) + 1
        else:
            language_counts[language] = language_counts.get(language, 0) + 1
        file_path = doc.metadata.get("file_path", "").lower()
        content = doc.page_content.lower()

        if file_path.endswith("package.json"):
            if "react" in content:
                frameworks.add("React")
            if "next" in content:
                frameworks.add("Next.js")
            if "express" in content:
                frameworks.add("Express")
            if "vite" in content:
                frameworks.add("Vite")
        if "fastapi" in content:
            frameworks.add("FastAPI")
        if "django" in content:
            frameworks.add("Django")
        if "flask" in content:
            frameworks.add("Flask")
        if "langchain" in content:
            frameworks.add("LangChain")
        if "chromadb" in content:
            frameworks.add("ChromaDB")

    languages = [
        {"name": name, "files": count}
        for name, count in sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    configs = [
        {"name": name, "files": count}
        for name, count in sorted(config_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "languages": languages,
        "configs": configs,
        "frameworks_libraries": sorted(frameworks),
        "summary": ", ".join([item["name"] for item in languages[:5]]) or "No supported source files detected"
    }


def build_module_problems(issues):
    modules = {}

    for issue in issues:
        module = issue.get("module") or module_name_from_path(issue.get("file_path", ""))
        data = modules.setdefault(module, {
            "module": module,
            "issue_count": 0,
            "high": 0,
            "medium": 0,
            "files": set(),
            "major_problem": ""
        })
        data["issue_count"] += 1
        data["files"].add(issue.get("file_path", ""))

        severity = str(issue.get("severity", "")).lower()
        if severity == "high":
            data["high"] += 1
        elif severity == "medium":
            data["medium"] += 1

    module_problems = []
    for data in modules.values():
        files = sorted(file_path for file_path in data["files"] if file_path)
        data["files"] = files
        data["major_problem"] = (
            f"{data['module']} has {data['issue_count']} confirmed issue(s) "
            f"across {len(files)} file(s)."
        )
        module_problems.append(data)

    return sorted(module_problems, key=lambda item: (-item["high"], -item["medium"], item["module"]))


def detect_developed_modules(documents):
    modules = {}

    for doc in documents:
        file_path = doc.metadata.get("file_path", "")
        module = module_name_from_path(file_path)
        language = doc.metadata.get("language", "unknown")
        data = modules.setdefault(module, {
            "name": module,
            "file_count": 0,
            "languages": set(),
            "sample_files": []
        })

        data["file_count"] += 1
        data["languages"].add(language)

        if len(data["sample_files"]) < 5:
            data["sample_files"].append(file_path)

    developed_modules = []
    for data in modules.values():
        data["languages"] = sorted(data["languages"])
        developed_modules.append(data)

    return sorted(developed_modules, key=lambda item: (-item["file_count"], item["name"]))


def build_severity_vulnerability_summary(issues):
    return {
        "high": sum(1 for issue in issues if str(issue.get("severity", "")).lower() == "high"),
        "medium": sum(1 for issue in issues if str(issue.get("severity", "")).lower() == "medium"),
        "low": sum(1 for issue in issues if str(issue.get("severity", "")).lower() == "low"),
        "vulnerabilities": sum(1 for issue in issues if issue.get("vulnerability")),
        "review_standard": "Only confirmed, evidence-backed issues are included."
    }


def build_review_sections(documents, issues):
    normalized_issues = normalize_review_issues(issues)

    return {
        "tech_stack": detect_tech_stack(documents),
        "developed_modules": detect_developed_modules(documents),
        "module_problems": build_module_problems(normalized_issues),
        "severity_vulnerability": build_severity_vulnerability_summary(normalized_issues),
        "issues": normalized_issues
    }


def review_single_file_safe(doc, question: str):
    max_retries = int(os.getenv("FULL_REVIEW_RATE_LIMIT_RETRIES", "4"))
    retry_wait_seconds = float(os.getenv("FULL_REVIEW_RATE_LIMIT_WAIT_SECONDS", "60"))

    for attempt in range(max_retries + 1):
        try:
            result = review_single_file(doc, question)
            issues = result.get("issues", [])

            if isinstance(issues, list):
                return issues

            return []

        except Exception as e:
            if is_rate_limit_error(e) and attempt < max_retries:
                time.sleep(retry_wait_seconds * (attempt + 1))
                continue

            return [{
                "file_path": doc.metadata.get("file_path", ""),
                "module": module_name_from_path(doc.metadata.get("file_path", "")),
                "issue_type": "review_error",
                "severity": "medium",
                "confidence": "high",
                "vulnerability": False,
                "problem": f"Could not review this file: {str(e)}",
                "why_it_is_problem": "The LLM or parser failed while reviewing this file.",
                "evidence": str(e),
                "suggestion": "Try reviewing this file separately or reduce file size.",
                "improved_code": {
                    "language": doc.metadata.get("language", ""),
                    "code": ""
                }
            }]


def bounded_worker_count(requested_workers: int, document_count: int):
    try:
        env_workers = int(os.getenv("FULL_REVIEW_WORKERS", "1"))
    except ValueError:
        env_workers = 1

    if requested_workers and requested_workers != 1 and os.getenv("FULL_REVIEW_ALLOW_REQUEST_WORKERS", "false").lower() == "true":
        env_workers = requested_workers

    return max(1, min(env_workers, 10, max(document_count, 1)))


def full_project_review(repo_id: str, question: str, max_workers: int = 1):
    repo_path = get_repo_source_path(repo_id)

    if not repo_path.exists():
        return {
            "summary": "Repository not found",
            "tech_stack": {},
            "developed_modules": [],
            "module_problems": [],
            "issues": [],
            "severity_vulnerability": {},
            "overall_improvements": []
        }

    documents = read_repo.load_documents(repo_path)

    all_issues = []

    try:
        syntax_result = check_project_syntax(repo_path)
        all_issues.extend([
            syntax_issue_to_review_issue(issue)
            for issue in syntax_result.get("issues", [])
        ])
    except Exception as e:
        all_issues.append({
            "file_path": "",
            "module": "root",
            "issue_type": "review_error",
            "severity": "medium",
            "confidence": "high",
            "vulnerability": False,
            "problem": f"Could not run syntax check: {str(e)}",
            "why_it_is_problem": "The syntax checker failed before full review completed.",
            "evidence": str(e),
            "suggestion": "Check syntax checker dependencies and retry.",
            "improved_code": {
                "language": "",
                "code": ""
            }
        })

    worker_count = bounded_worker_count(max_workers, len(documents))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        reviewed_issue_groups = executor.map(
            lambda doc: review_single_file_safe(doc, question),
            documents
        )

        for issues in reviewed_issue_groups:
            all_issues.extend(issues)

    sections = build_review_sections(documents, all_issues)

    return {
        "summary": f"Full project review completed. Reviewed {len(documents)} files and found {len(all_issues)} issues.",
        "tech_stack": sections["tech_stack"],
        "developed_modules": sections["developed_modules"],
        "module_problems": sections["module_problems"],
        "issues": sections["issues"],
        "severity_vulnerability": sections["severity_vulnerability"],
        "file_filter": dict(read_repo.LAST_LOAD_STATS),
        "overall_improvements": [
            "Tech stack is reported first from detected file languages and known dependency/config files.",
            "Findings are grouped into module-level problems and per-file defects.",
            f"File filter loaded {read_repo.LAST_LOAD_STATS.get('loaded', 0)} files and skipped {read_repo.LAST_LOAD_STATS.get('ignored', 0) + read_repo.LAST_LOAD_STATS.get('style_skipped', 0) + read_repo.LAST_LOAD_STATS.get('unsupported', 0) + read_repo.LAST_LOAD_STATS.get('too_large', 0)} irrelevant, style-only, or unsupported files.",
            f"Full review used {worker_count} parallel workers.",
            "The prompt filters speculative or low-confidence findings to reduce unnecessary bugs."
        ]
    }


def stream_event(event_type: str, **payload):
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


def full_project_review_stream(repo_id: str, question: str, max_workers: int = 1):
    repo_path = get_repo_source_path(repo_id)

    if not repo_path.exists():
        yield stream_event(
            "done",
            result={
                "summary": "Repository not found",
                "tech_stack": {},
                "developed_modules": [],
                "module_problems": [],
                "issues": [],
                "severity_vulnerability": {},
                "overall_improvements": []
            }
        )
        return

    yield stream_event("status", message="Loading repository files...")
    documents = read_repo.load_documents(repo_path)
    worker_count = bounded_worker_count(max_workers, len(documents))
    all_issues = []

    yield stream_event("section", name="tech_stack", data=detect_tech_stack(documents))
    yield stream_event("section", name="developed_modules", data=detect_developed_modules(documents))
    yield stream_event(
        "status",
        message=f"Reviewing {len(documents)} files. Findings will appear as each file finishes.",
        reviewed_files=0,
        total_files=len(documents),
        total_issues=0
    )

    try:
        syntax_result = check_project_syntax(repo_path)
        syntax_issues = [
            syntax_issue_to_review_issue(issue)
            for issue in syntax_result.get("issues", [])
        ]
        all_issues.extend(syntax_issues)

        for issue in syntax_issues:
            yield stream_event("issue", issue=issue, reviewed_files=0, total_files=len(documents), total_issues=len(all_issues))
    except Exception as e:
        issue = {
            "file_path": "",
            "module": "root",
            "issue_type": "review_error",
            "severity": "medium",
            "confidence": "high",
            "vulnerability": False,
            "problem": f"Could not run syntax check: {str(e)}",
            "why_it_is_problem": "The syntax checker failed before full review completed.",
            "evidence": str(e),
            "suggestion": "Check syntax checker dependencies and retry.",
            "improved_code": {
                "language": "",
                "code": ""
            }
        }
        all_issues.append(issue)
        yield stream_event("issue", issue=issue, reviewed_files=0, total_files=len(documents), total_issues=len(all_issues))

    reviewed_files = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_doc = {
            executor.submit(review_single_file_safe, doc, question): doc
            for doc in documents
        }

        for future in as_completed(future_to_doc):
            doc = future_to_doc[future]
            reviewed_files += 1
            issues = future.result()
            all_issues.extend(issues)

            for issue in issues:
                yield stream_event(
                    "issue",
                    issue=issue,
                    reviewed_files=reviewed_files,
                    total_files=len(documents),
                    total_issues=len(all_issues)
                )

            yield stream_event(
                "file_done",
                file_path=doc.metadata.get("file_path", ""),
                reviewed_files=reviewed_files,
                total_files=len(documents),
                total_issues=len(all_issues)
            )

    sections = build_review_sections(documents, all_issues)
    result = {
        "summary": f"Full project review completed. Reviewed {len(documents)} files and found {len(all_issues)} issues.",
        "tech_stack": sections["tech_stack"],
        "developed_modules": sections["developed_modules"],
        "module_problems": sections["module_problems"],
        "issues": sections["issues"],
        "severity_vulnerability": sections["severity_vulnerability"],
        "file_filter": dict(read_repo.LAST_LOAD_STATS),
        "overall_improvements": [
            "Tech stack is reported first from detected file languages and known dependency/config files.",
            "Findings are grouped into module-level problems and per-file defects.",
            f"File filter loaded {read_repo.LAST_LOAD_STATS.get('loaded', 0)} files and skipped {read_repo.LAST_LOAD_STATS.get('ignored', 0) + read_repo.LAST_LOAD_STATS.get('style_skipped', 0) + read_repo.LAST_LOAD_STATS.get('unsupported', 0) + read_repo.LAST_LOAD_STATS.get('too_large', 0)} irrelevant, style-only, or unsupported files.",
            f"Full review used {worker_count} parallel workers.",
            "The prompt filters speculative or low-confidence findings to reduce unnecessary bugs."
        ]
    }

    yield stream_event("done", result=result)



@router.post("/full-review")
def full_review(request: FullReviewRequest):
    return StreamingResponse(
        full_project_review_stream(
            repo_id=request.repo_id,
            question=request.question,
            max_workers=request.max_workers
        ),
        media_type="application/x-ndjson"
    )
