import json
from langchain_chroma import Chroma
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def vectorstore_path(repo_id: str):
    return Path(f'chromadb/{repo_id}')


def vectorstore_exists(repo_id: str):
    persist_directory = vectorstore_path(repo_id)
    return (
        persist_directory.exists()
        and any(path.name != "index_metadata.json" for path in persist_directory.iterdir())
    )


def index_metadata_path(repo_id: str):
    return vectorstore_path(repo_id) / "index_metadata.json"


def get_index_metadata(repo_id: str):
    metadata_path = index_metadata_path(repo_id)

    if not metadata_path.exists():
        return None

    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_index_metadata(repo_id: str, files_loaded: int, chunks_created: int, source_path: str | None = None):
    metadata_path = index_metadata_path(repo_id)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "files_loaded": files_loaded,
        "chunks_created": chunks_created
    }

    if source_path:
        metadata["source_path"] = source_path

    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def get_repo_source_path(repo_id: str):
    metadata = get_index_metadata(repo_id) or {}
    source_path = metadata.get("source_path")

    if source_path:
        return Path(source_path)

    return Path("repos") / repo_id


def create_vectorstore(chunks,repo_id:str):
    persist_directory = vectorstore_path(repo_id)

    if vectorstore_exists(repo_id):
        return Chroma(
            persist_directory=str(persist_directory),
            embedding_function=embeddings
        )

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(persist_directory)
    )
