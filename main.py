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


@app.middleware("http")
async def add_frontend_no_cache_headers(request, call_next):
    response = await call_next(request)

    if request.url.path in {"/", "/index.html", "/app.js", "/styles.css"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
