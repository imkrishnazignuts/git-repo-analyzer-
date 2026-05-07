from langchain_text_splitters import RecursiveCharacterTextSplitter

spiltter = RecursiveCharacterTextSplitter(
    chunk_size = 1500,
    chunk_overlap = 100
)

def split_document(documents):
    return spiltter.split_documents(documents)
