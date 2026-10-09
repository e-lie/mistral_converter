import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mistral_converter.core.book import Book, Step
from mistral_converter.core.metadata import Metadata
from mistral_converter.core.mistral import MistralApi, MistralClient
from mistral_converter.core.ocr import ocr_document
from mistral_converter.core.steps import epub_book, fix_book
from mistral_converter.web import storage
from mistral_converter.web.jobs import JobQueue
from mistral_converter.web.secret import KeyStore, RbwRun, run_rbw
from mistral_converter.web.settings import Settings

CHUNK = 1024 * 1024
FILE_KINDS = {
    "pdf": lambda b: b.pdf,
    "ocr": lambda b: b.ocr_json,
    "fixed": lambda b: b.fixed_json,
    "md": lambda b: b.markdown,
    "epub": lambda b: b.epub,
}
STEP_NAMES = {step.value: step for step in Step}
STEP_LABELS = {Step.OCR: "OCR", Step.FIX: "Heading fix", Step.EPUB: "EPUB"}


def create_app(
    settings: Settings | None = None,
    api: MistralApi | None = None,
    rbw: RbwRun = run_rbw,
    api_factory: Callable[[str], MistralApi] = lambda key: MistralClient(key),
) -> FastAPI:
    """Without an explicit `api`, the Mistral key is read from rbw and the API built from it."""
    settings = settings or Settings.from_env()
    app = FastAPI(root_path=settings.root_path)
    app.state.settings = settings
    app.state.api = api
    keys = app.state.keys = KeyStore(settings.rbw_item, settings.rbw_user, rbw, settings.rbw_retry_seconds)
    if api is None and settings.rbw_item:
        keys.start()
    built: dict[str, MistralApi] = {}

    def current_api() -> MistralApi | None:
        if app.state.api is not None:
            return app.state.api
        key = keys.key
        if key is None:
            return None
        if key not in built:
            built.clear()
            built[key] = api_factory(key)
        return built[key]

    def require_api() -> MistralApi:
        found = current_api()
        if found is None:
            raise HTTPException(503, "The Mistral API key is unavailable")
        return found
    jobs = app.state.jobs = JobQueue()
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

    def current_user(request: Request) -> str:
        user = request.headers.get(settings.user_header) or settings.dev_user
        if not user:
            raise HTTPException(401, "Not signed in")
        try:
            storage.user_base(settings.data_dir, user)
        except storage.InvalidPath as error:
            raise HTTPException(400, str(error))
        return user

    def folder_of(user: str, subfolder: str):
        try:
            return storage.working_folder(settings.data_dir, user, subfolder)
        except storage.InvalidPath as error:
            raise HTTPException(400, str(error))

    def books_context(request: Request, user: str, folder: str) -> dict:
        books = []
        if folder:
            for book in folder_of(user, folder).books():
                states = {step: jobs.state(book, step) for step in Step}
                books.append(
                    {
                        "stem": book.stem,
                        "states": states,
                        "busy": any(state == "running" for state, _ in states.values()),
                        "files": [k for k, f in FILE_KINDS.items() if f(book).exists()],
                    }
                )
        return {
            "root": request.scope.get("root_path", ""),
            "folder": folder,
            "books": books,
            "labels": STEP_LABELS,
            "ocr_step": Step.OCR,
            "key_ok": current_api() is not None,
            "unlock_hint": settings.unlock_hint,
            "polling": any(b["busy"] for b in books),
            "q": quote,
        }

    def page(request: Request, user: str, folder: str = "", error: str | None = None, status: int = 200):
        context = books_context(request, user, folder)
        context |= {
            "user": user,
            "folders": storage.subfolders(settings.data_dir, user),
            "max_mb": settings.max_upload_mb,
            "error": error,
        }
        return templates.TemplateResponse(request, "index.html", context, status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if error.status_code == 401:
            return HTMLResponse(error.detail, status_code=401)
        user = request.headers.get(settings.user_header) or settings.dev_user
        try:
            storage.user_base(settings.data_dir, user or "")
        except storage.InvalidPath:
            return HTMLResponse(error.detail, status_code=error.status_code)
        return page(request, user, error=error.detail, status=error.status_code)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, folder: str = ""):
        return page(request, current_user(request), folder.strip())

    @app.post("/upload")
    async def upload(request: Request, folder: str = Form(...), file: UploadFile | None = None):
        user = current_user(request)
        folder = folder.strip()
        working = folder_of(user, folder)
        if file is None or not file.filename:
            raise HTTPException(400, "Choose a PDF file")
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are accepted")
        target = working.path / (storage.stem_from_filename(file.filename) + ".pdf")
        if target.exists():
            raise HTTPException(409, f"A book named {target.stem} already exists in this folder")
        working.path.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=working.path, prefix=".upload.")
        try:
            size = 0
            head = b""
            with os.fdopen(handle, "wb") as out:
                while chunk := await file.read(CHUNK):
                    head = head or chunk[:5]
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, f"File too large (limit {settings.max_upload_mb} MB)")
                    out.write(chunk)
            if head != b"%PDF-":
                raise HTTPException(400, "The file is not a valid PDF")
            os.replace(tmp, target)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return RedirectResponse(f"{request.scope.get('root_path', '')}/?folder={quote(folder)}", 303)

    def book_of(user: str, folder: str, stem: str) -> Book:
        if "/" in stem or "\\" in stem or stem.startswith("."):
            raise HTTPException(400, "Invalid request")
        return Book(folder_of(user, folder).path, stem)

    @app.get("/download")
    def download(request: Request, folder: str, stem: str, kind: str):
        user = current_user(request)
        if kind not in FILE_KINDS:
            raise HTTPException(400, "Invalid request")
        path = FILE_KINDS[kind](book_of(user, folder, stem))
        if not path.is_file():
            raise HTTPException(404, "File not found")
        return FileResponse(path, filename=path.name)

    @app.get("/books", response_class=HTMLResponse)
    def books_fragment(request: Request, folder: str):
        user = current_user(request)
        return templates.TemplateResponse(request, "_books.html", books_context(request, user, folder))

    def step_job(book: Book, step: Step, metadata: Metadata):
        if step is Step.OCR:
            api = require_api()
            return lambda: ocr_document(book.pdf, api)
        if step is Step.FIX:
            api = require_api()

            def fix():
                if not book.ocr_json.exists():
                    raise RuntimeError("OCR is not done")
                fix_book(book, api)

            return fix
        api = current_api()

        def epub():
            if not book.ocr_json.exists():
                raise RuntimeError("OCR is not done")
            epub_book(book, metadata, api)

        return epub

    @app.post("/steps/{name}", response_class=HTMLResponse)
    def start_step(
        request: Request,
        name: str,
        folder: str = Form(...),
        stem: str = Form(...),
        overwrite: bool = Form(False),
        title: str = Form(""),
        author: str = Form(""),
        language: str = Form(""),
        publisher: str = Form(""),
        date: str = Form(""),
    ):
        user = current_user(request)
        book = book_of(user, folder, stem)
        if not book.pdf.exists():
            raise HTTPException(404, "Book not found")
        metadata = Metadata(title=title, author=author, language=language, publisher=publisher, date=date)
        if name == "all":
            if jobs.is_busy(book):
                raise HTTPException(409, "A step is already running on this book")
            steps = [s for s in Step if overwrite or not book.is_done(s)]
            if not steps:
                raise HTTPException(409, "All steps are already done")
            work = [(s, step_job(book, s, metadata)) for s in steps]
        elif name in STEP_NAMES:
            step = STEP_NAMES[name]
            if step is not Step.OCR and not book.is_done(Step.OCR):
                raise HTTPException(409, "OCR must be done first")
            if book.is_done(step) and not overwrite:
                raise HTTPException(409, f"{STEP_LABELS[step]} is already done")
            work = [(step, step_job(book, step, metadata))]
        else:
            raise HTTPException(404, "Unknown step")
        for step, job in work:
            if not jobs.submit(book, step, job):
                raise HTTPException(409, f"{STEP_LABELS[step]} is already running")
        return templates.TemplateResponse(request, "_books.html", books_context(request, user, folder))

    @app.post("/delete")
    def delete(request: Request, folder: str = Form(...), stem: str = Form(...)):
        user = current_user(request)
        book = book_of(user, folder, stem)
        if not book.pdf.exists():
            raise HTTPException(404, "Book not found")
        if jobs.is_busy(book):
            raise HTTPException(409, "A step is running on this book")
        storage.delete_book(book)
        return RedirectResponse(f"{request.scope.get('root_path', '')}/?folder={quote(folder)}", 303)

    return app
