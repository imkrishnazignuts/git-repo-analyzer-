import json
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
from services.read_repo import load_documents
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from .review_code import llm, LLM_MODEL
from .syntax_check import check_project_syntax
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

class FullReviewRequest(BaseModel):
    repo_id: str
    question: str = "Review this project for bugs, syntax errors, security issues, runtime errors, and bad practices."
    max_workers: int = 2


full_review_stream_llm = ChatGroq(
    model=LLM_MODEL,
    temperature=0.2,
    streaming=True
)


full_review_prompt = ChatPromptTemplate.from_template("""
You are a senior software engineer and security-focused code reviewer.

Review the given file carefully.

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
      "issue_type": "bug | syntax_error | security | runtime_error | bad_practice | performance | improvement",
      "severity": "low | medium | high",
      "problem": "",
      "why_it_is_problem": "",
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
    chain = full_review_prompt | llm

    response = chain.invoke({
        "question": question,
        "file_path": doc.metadata.get("file_path", ""),
        "code": doc.page_content[:12000]
    })

    return parse_llm_json(response)


def stream_single_file_review(doc, question: str):
    chain = full_review_prompt | full_review_stream_llm
    content = []

    for chunk in chain.stream({
        "question": question,
        "file_path": doc.metadata.get("file_path", ""),
        "code": doc.page_content[:12000]
    }):
        token = getattr(chunk, "content", chunk)
        token = str(token)

        if not token:
            continue

        content.append(token)
        yield token

    parsed = parse_llm_json("".join(content))
    issues = parsed.get("issues", [])

    if isinstance(issues, list):
        return issues

    return []


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
        "issue_type": "syntax_error",
        "severity": "high",
        "problem": issue.get("problem", ""),
        "why_it_is_problem": f"{issue.get('language', 'Code')} syntax errors can break builds or runtime execution.",
        "suggestion": f"Fix the {issue.get('rule', 'syntax')} issue on line {issue.get('line')}.",
        "improved_code": {
            "language": issue.get("language", ""),
            "code": issue.get("code", "")
        }
    }


def review_single_file_safe(doc, question: str):
    try:
        result = review_single_file(doc, question)
        issues = result.get("issues", [])

        if isinstance(issues, list):
            return issues

        return []

    except Exception as e:
        return [{
            "file_path": doc.metadata.get("file_path", ""),
            "issue_type": "review_error",
            "severity": "medium",
            "problem": f"Could not review this file: {str(e)}",
            "why_it_is_problem": "The LLM or parser failed while reviewing this file.",
            "suggestion": "Try reviewing this file separately or reduce file size.",
            "improved_code": {
                "language": doc.metadata.get("language", ""),
                "code": ""
            }
        }]


def bounded_worker_count(requested_workers: int, document_count: int):
    try:
        env_workers = int(os.getenv("FULL_REVIEW_WORKERS", requested_workers or 2))
    except ValueError:
        env_workers = requested_workers or 2

    return max(1, min(env_workers, 10, max(document_count, 1)))


def full_project_review(repo_id: str, question: str, max_workers: int = 2):
    repo_path = Path(f"repos/{repo_id}")

    if not repo_path.exists():
        return {
            "summary": "Repository not found",
            "issues": [],
            "overall_improvements": []
        }

    documents = load_documents(repo_path)

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
            "issue_type": "review_error",
            "severity": "medium",
            "problem": f"Could not run syntax check: {str(e)}",
            "why_it_is_problem": "The syntax checker failed before full review completed.",
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

    return {
        "summary": f"Full project review completed. Reviewed {len(documents)} files and found {len(all_issues)} issues.",
        "issues": all_issues,
        "overall_improvements": [
            "Use full-review mode for complete project scanning.",
            "Use normal /ai/ask mode for fast question-answering on selected project context.",
            f"Full review used {worker_count} parallel workers.",
            "Syntax checks are run before LLM review for faster deterministic syntax findings."
        ]
    }


def stream_event(event_type: str, **payload):
    return json.dumps({"type": event_type, **payload}) + "\n"


def full_project_review_stream(repo_id: str, question: str, max_workers: int = 2):
    repo_path = Path(f"repos/{repo_id}")

    if not repo_path.exists():
        yield stream_event(
            "complete",
            summary="Repository not found",
            reviewed_files=0,
            total_files=0,
            total_issues=0
        )
        return

    documents = load_documents(repo_path)
    all_issues = []
    reviewed_files = 0

    yield stream_event(
        "status",
        message=f"Loaded {len(documents)} files. Starting LLM stream.",
        reviewed_files=reviewed_files,
        total_files=len(documents),
        total_issues=len(all_issues)
    )

    worker_count = bounded_worker_count(max_workers, len(documents))
    yield stream_event(
        "status",
        message=f"Streaming LLM tokens file by file. Requested workers: {worker_count}.",
        reviewed_files=reviewed_files,
        total_files=len(documents),
        total_issues=len(all_issues)
    )

    for doc in documents:
        file_path = doc.metadata.get("file_path", "")

        yield stream_event(
            "file_start",
            file_path=file_path,
            language=doc.metadata.get("language", ""),
            reviewed_files=reviewed_files,
            total_files=len(documents),
            total_issues=len(all_issues)
        )

        try:
            token_stream = stream_single_file_review(doc, question)

            while True:
                try:
                    token = next(token_stream)
                    yield stream_event(
                        "token",
                        file_path=file_path,
                        token=token,
                        reviewed_files=reviewed_files,
                        total_files=len(documents),
                        total_issues=len(all_issues)
                    )
                except StopIteration as finished:
                    issues = finished.value or []
                    break

            reviewed_files += 1

            for issue in issues:
                all_issues.append(issue)
                yield stream_event(
                    "issue",
                    issue=issue,
                    reviewed_files=reviewed_files,
                    total_files=len(documents),
                    total_issues=len(all_issues)
                )

            yield stream_event(
                "file_complete",
                file_path=file_path,
                issue_count=len(issues),
                reviewed_files=reviewed_files,
                total_files=len(documents),
                total_issues=len(all_issues)
            )

        except Exception as e:
            reviewed_files += 1
            review_issue = {
                "file_path": file_path,
                "issue_type": "review_error",
                "severity": "medium",
                "problem": f"Could not review this file: {str(e)}",
                "why_it_is_problem": "The LLM or parser failed while reviewing this file.",
                "suggestion": "Try reviewing this file separately or reduce file size.",
                "improved_code": {
                    "language": doc.metadata.get("language", ""),
                    "code": ""
                }
            }
            all_issues.append(review_issue)
            yield stream_event(
                "issue",
                issue=review_issue,
                reviewed_files=reviewed_files,
                total_files=len(documents),
                total_issues=len(all_issues)
            )
            yield stream_event(
                "file_complete",
                file_path=file_path,
                issue_count=1,
                reviewed_files=reviewed_files,
                total_files=len(documents),
                total_issues=len(all_issues)
            )

    yield stream_event(
        "status",
        message="LLM stream finished. Running syntax checks.",
        reviewed_files=reviewed_files,
        total_files=len(documents),
        total_issues=len(all_issues)
    )

    try:
        syntax_result = check_project_syntax(repo_path)
        for issue in syntax_result.get("issues", []):
            review_issue = syntax_issue_to_review_issue(issue)
            all_issues.append(review_issue)
            yield stream_event(
                "issue",
                issue=review_issue,
                reviewed_files=reviewed_files,
                total_files=len(documents),
                total_issues=len(all_issues)
            )
    except Exception as e:
        review_issue = {
            "file_path": "",
            "issue_type": "review_error",
            "severity": "medium",
            "problem": f"Could not run syntax check: {str(e)}",
            "why_it_is_problem": "The syntax checker failed after LLM review completed.",
            "suggestion": "Check syntax checker dependencies and retry.",
            "improved_code": {
                "language": "",
                "code": ""
            }
        }
        all_issues.append(review_issue)
        yield stream_event(
            "issue",
            issue=review_issue,
            reviewed_files=reviewed_files,
            total_files=len(documents),
            total_issues=len(all_issues)
        )

    yield stream_event(
        "complete",
        summary=f"Full project review completed. Reviewed {len(documents)} files and found {len(all_issues)} issues.",
        reviewed_files=reviewed_files,
        total_files=len(documents),
        total_issues=len(all_issues),
        overall_improvements=[
            "Use full-review mode for complete project scanning.",
            "Use normal /ai/ask mode for fast question-answering on selected project context.",
            "Full review streamed model output as each file was reviewed.",
            "Syntax checks are run before LLM review for faster deterministic syntax findings."
        ]
    )



@router.post("/full-review")
def full_review(request: FullReviewRequest):
    return StreamingResponse(
        full_project_review_stream(
            repo_id=request.repo_id,
            question=request.question,
            max_workers=request.max_workers
        ),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
