from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from services.review_code import router
from dotenv import load_dotenv
from pathlib import Path

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

load_dotenv()
app.include_router(router)
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
