import shutil
import os
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from .chromadb_setup import Chroma,embeddings
from langchain_core.output_parsers import JsonOutputParser
from fastapi import APIRouter
from pydantic import BaseModel
from .repo_clone_service import clone_repo
from .spiltter import split_document
from .chromadb_setup import create_vectorstore, get_index_metadata, save_index_metadata, vectorstore_exists
from .read_repo import load_documents
from dotenv import load_dotenv

load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

prompt = ChatPromptTemplate.from_template(
    """
You are an expert senior software engineer, code analyst, and repository assistant.

Your job is to answer the user's question ONLY using the provided code context.

You must:
- Understand the repository structure.
- Identify functions, classes, APIs, variables, models, routes, imports, and logic.
- Answer repository-related questions accurately.
- If a function, class, or variable exists, mention:
  - file path
  - line number if available
  - short explanation
- If something does not exist in the provided context, clearly say so.
- If relevant, explain how different files are connected.

You can answer questions like:
- Does get_data function exist?
- Where is authentication implemented?
- Which file handles vector DB logic?
- Where is JWT verified?
- Which API endpoint creates users?
- How does the RAG pipeline work?
- Which file contains database models?
- Is async/await used?
- Where is ChromaDB initialized?

Code Context:
{context}

User Question:
{question}

Return ONLY valid JSON.

VERY IMPORTANT:
- Do not use markdown.
- Do not use triple backticks.
- Do not use ```json.
- Do not explain outside JSON.
- Always return valid parsable JSON.
- If line number is unavailable, return null.
- Never hallucinate files or functions.
- Use ONLY the provided context.

Return response in this exact format:

{{
  "answer": "",
  "found": true,
  "results": [
    {{
      "file_path": "",
      "line_number": null,
      "symbol_type": "function | class | variable | api | model | import | route | module",
      "name": "",
      "description": ""
    }}
  ],
  "related_files": [],
  "suggestions": []
}}


"""
)


llm = ChatGroq(
    model=LLM_MODEL,
    temperature=0.2
)


def review_code(repo_id:str , question:str):
    vectorstore = Chroma(
        persist_directory=f'chromadb/{repo_id}',
        embedding_function=embeddings
    )

    retriever = vectorstore.as_retriever(search_kwargs = {"k":5})

    docs = retriever.invoke(question)
    context = "\n\n".join([
        f"File: {doc.metadata.get('file_path')}\nCode:\n{doc.page_content}"
        for doc in docs
    ])

    chain = prompt | llm | JsonOutputParser()

    return chain.invoke(
        {
            "question":question,
            "context":context
        }
    )


class requestRepo(BaseModel):
    repo_link:str
    force_reindex: bool = False

class reviewRequest(BaseModel):
    repo_id :str
    question:str


@router.post('/index')
def index_repo(request : requestRepo):
    repo = clone_repo(request.repo_link, request.force_reindex)

    if request.force_reindex:
        shutil.rmtree(Path("chromadb") / repo["repo_id"], ignore_errors=True)

    metadata = get_index_metadata(repo["repo_id"])

    if repo.get("cached") and vectorstore_exists(repo["repo_id"]) and metadata:
        return {
            "message": "Repository indexed successfully",
            "repo_id": repo["repo_id"],
            "cached": True,
            "files_loaded": metadata.get("files_loaded", 0),
            "chunks_created": metadata.get("chunks_created", 0)
        }

    documents = load_documents(repo["path"])
    chunks = split_document(documents)

    create_vectorstore(chunks,repo["repo_id"])
    save_index_metadata(repo["repo_id"], len(documents), len(chunks))

    return {
        "message": "Repository indexed successfully",
        "repo_id": repo["repo_id"],
        "cached": repo.get("cached", False),
        "files_loaded": len(documents),
        "chunks_created": len(chunks)
    }

@router.post('/ask')
def ask_question_in_repo(request:reviewRequest):
    result = review_code(repo_id=request.repo_id,question=request.question)
    return result
