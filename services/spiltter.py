from langchain_text_splitters import RecursiveCharacterTextSplitter

spiltter = RecursiveCharacterTextSplitter(
    chunk_size = 1500,
    chunk_overlap = 200
)

def split_document(documents):
    return spiltter.split_documents(documents)