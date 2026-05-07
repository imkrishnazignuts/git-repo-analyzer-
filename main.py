from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from services.review_code import router
from dotenv import load_dotenv
from pathlib import Path
from services.full_review_code import router as full_review_router
from services.syntax_check import router as syntax_check_router
from services.zip_file_review import router as zip_router

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

load_dotenv()
app.include_router(router)
app.include_router(full_review_router)
app.include_router(syntax_check_router)
app.include_router(zip_router)
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
