from langchain_chroma import Chroma
from langchain_huggingface.embeddings import HuggingFaceEmbeddings


embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def create_vectorstore(chunks,repo_id:str):
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=f'chromadb/{repo_id}'
    )


    