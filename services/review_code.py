from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from .chromadb_setup import Chroma,embeddings
from langchain_core.output_parsers import JsonOutputParser
from fastapi import APIRouter
from pydantic import BaseModel
from .repo_clone_service import clone_repo
from .spiltter import split_document
from .chromadb_setup import create_vectorstore 
from .read_repo import load_documents
from dotenv import load_dotenv

load_dotenv()
router = APIRouter(
    prefix='/ai',
    tags=['Review Code']
)

prompt = ChatPromptTemplate.from_template(
    """
You are a senior software engineer and security-focused code reviewer.

Analyze the given code context.

Find:
1. Bugs
2. Runtime errors
3. Security issues
4. Bad practices
5. Performance issues
6. Code improvement ideas
7. Better implementation suggestions

Code Context:
{context}

User Question:
{question}

Return ONLY valid JSON.
verify the json and give only in this format 

VERY IMPORTANT:
- Do not use markdown.
- Do not use ```python.
- Do not use triple backticks.
- improved_code must contain raw code only.
- Never wrap code in markdown fences.

Format:
{{
  "summary": "",
  "issues": [
    {{
      "file_path": "",
      "issue_type": "",
      "severity": "low | medium | high",
      "problem": "",
      "why_it_is_problem": "",
      "suggestion": "",
      "improved_code": {{
        "language": "",
        "code": ""
      }}
    }}
  ],
  "overall_improvements": []
}}



"""
)


llm = ChatGroq(
    model="openai/gpt-oss-120b",
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

class reviewRequest(BaseModel):
    repo_id :str
    question:str


@router.post('/index')
def index_repo(request : requestRepo):
    repo = clone_repo(request.repo_link)

    documents = load_documents(repo["path"])
    chunks = split_document(documents)

    create_vectorstore(chunks,repo["repo_id"])

    return {
        "message": "Repository indexed successfully",
        "repo_id": repo["repo_id"],
        "files_loaded": len(documents),
        "chunks_created": len(chunks)
    }

@router.post('/ask')
def ask_question_in_repo(request:reviewRequest):
    result = review_code(repo_id=request.repo_id,question=request.question)
    return result
    