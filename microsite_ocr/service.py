"""Service HTTP: tiket → DMS-Cardsys → OCR API, hasil dikembalikan sebagai JSON.

Contoh:
    python -m microsite_ocr.service
    curl localhost:8090/tickets/081156CqJu/ocr
    curl localhost:8090/tickets/081156CqJu/ocr/ktp
"""
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Path as PathParam, Request, Security
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from .cli import LOG_FORMAT
from .config import Settings
from .dms_client import DmsClient
from .face_client import FaceClient
from .documents import DocumentType
from .ocr_client import OcrClient
from .openapi_examples import (
    HEALTH_RESPONSES,
    TICKET_BY_TYPE_RESPONSES,
    TICKET_ID_EXAMPLES,
    TICKET_RESPONSES,
    TICKETS_BY_TYPE_RESPONSES,
    TICKETS_REQUEST_EXAMPLES,
    TICKETS_RESPONSES,
)
from .pipeline import TicketOcrPipeline, TicketResult
from .store import OcrStore

logger = logging.getLogger(__name__)

# Disalin dari /data/ocr-qwen supaya /docs tetap jalan tanpa akses internet.
SWAGGER_UI_DIR = Path(__file__).parent / "static" / "swagger-ui"
HEALTH_TIMEOUT_SECONDS = 3.0
# Nomor tiket dikirim apa adanya ke DMS, jadi karakternya dibatasi.
TICKET_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

TicketId = Annotated[str, StringConstraints(pattern=TICKET_ID_PATTERN)]
TicketIdPath = Annotated[
    str, PathParam(pattern=TICKET_ID_PATTERN, description="Nomor tiket (NomorDokumen)", openapi_examples=TICKET_ID_EXAMPLES)
]
OcrDocType = Annotated[Literal["ktp", "npwp"], PathParam(description="Jenis dokumen yang di-OCR")]


class TicketsRequest(BaseModel):
    ticket_ids: list[TicketId] = Field(min_length=1, examples=[["081156CqJu", "020803XGC9"]])


TicketsBody = Annotated[TicketsRequest, Body(openapi_examples=TICKETS_REQUEST_EXAMPLES)]


class HealthResponse(BaseModel):
    status: str = Field(description='"ok" bila DMS dan OCR API siap, selain itu "degraded"')
    dms_reachable: bool
    ocr_ready: bool


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.api_key:
            logger.warning("SERVICE_API_KEY kosong: service berjalan tanpa autentikasi")
        if not store:
            logger.warning("DATABASE_URL kosong: hasil tidak disimpan ke database")
        elif not face:
            logger.warning("FACE_API_KEY kosong: face similarity tidak dihitung")
        with TicketOcrPipeline(
            dms=dms, ocr=ocr, max_workers=settings.max_workers, store=store, face=face
        ) as pipeline:
            app.state.pipeline = pipeline
            yield

    dms = DmsClient.from_settings(settings)
    ocr = OcrClient.from_settings(settings)
    store = OcrStore.from_settings(settings)
    face = FaceClient.from_settings(settings)

    app = FastAPI(
        title="Microsite OCR Service",
        description="Ambil dokumen KTP/NPWP dari DMS-Cardsys berdasarkan nomor tiket (NomorDokumen), "
                    "lalu ekstrak datanya lewat OCR API.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    _add_docs_routes(app)
    require_api_key = _api_key_dependency(settings)

    @app.get("/health", response_model=HealthResponse, tags=["System"], responses=HEALTH_RESPONSES)
    def health() -> HealthResponse:
        dms_reachable = dms.is_reachable(HEALTH_TIMEOUT_SECONDS)
        ocr_ready = ocr.is_ready(HEALTH_TIMEOUT_SECONDS)
        return HealthResponse(
            status="ok" if dms_reachable and ocr_ready else "degraded",
            dms_reachable=dms_reachable,
            ocr_ready=ocr_ready,
        )

    @app.get(
        "/tickets/{ticket_id}/ocr",
        response_model=TicketResult,
        dependencies=[Depends(require_api_key)],
        tags=["OCR"],
        summary="OCR semua KTP/NPWP dalam satu tiket",
        responses=TICKET_RESPONSES,
    )
    def ocr_ticket(request: Request, ticket_id: TicketIdPath) -> TicketResult:
        return _run_one(request, ticket_id, doc_types=None)

    @app.get(
        "/tickets/{ticket_id}/ocr/{doc_type}",
        response_model=TicketResult,
        dependencies=[Depends(require_api_key)],
        tags=["OCR"],
        summary="OCR KTP saja atau NPWP saja dalam satu tiket",
        description="Hanya dokumen jenis `doc_type` yang di-download dan di-OCR; jenis lain dicatat di `skipped`.",
        responses=TICKET_BY_TYPE_RESPONSES,
    )
    def ocr_ticket_by_type(request: Request, ticket_id: TicketIdPath, doc_type: OcrDocType) -> TicketResult:
        return _run_one(request, ticket_id, doc_types=[DocumentType(doc_type)])

    @app.post(
        "/tickets/ocr",
        response_model=list[TicketResult],
        dependencies=[Depends(require_api_key)],
        tags=["OCR"],
        summary="OCR KTP/NPWP beberapa tiket sekaligus",
        description="Hasil berurutan sesuai input, tanpa duplikat. Kegagalan per tiket ditandai di `error`, "
                    "tidak membuat request gagal.",
        responses=TICKETS_RESPONSES,
    )
    def ocr_tickets(request: Request, body: TicketsBody) -> list[TicketResult]:
        return _run_many(request, body, doc_types=None)

    @app.post(
        "/tickets/ocr/{doc_type}",
        response_model=list[TicketResult],
        dependencies=[Depends(require_api_key)],
        tags=["OCR"],
        summary="OCR KTP saja atau NPWP saja untuk beberapa tiket",
        description="Sama dengan `POST /tickets/ocr`, tetapi hanya dokumen jenis `doc_type` yang di-OCR; "
                    "jenis lain dicatat di `skipped`.",
        responses=TICKETS_BY_TYPE_RESPONSES,
    )
    def ocr_tickets_by_type(request: Request, body: TicketsBody, doc_type: OcrDocType) -> list[TicketResult]:
        return _run_many(request, body, doc_types=[DocumentType(doc_type)])

    def _run_one(request: Request, ticket_id: str, doc_types: list[DocumentType] | None) -> TicketResult:
        [result] = _pipeline(request).run([ticket_id], doc_types)
        # Tiket tidak ditemukan bukan error (`data: []`); dokumen yang gagal OCR ditandai di `data[].error`.
        if result.error:
            raise HTTPException(status_code=502, detail=f"Search DMS gagal: {result.error}")
        return result

    def _run_many(request: Request, body: TicketsRequest, doc_types: list[DocumentType] | None) -> list[TicketResult]:
        ticket_ids = list(dict.fromkeys(body.ticket_ids))
        if len(ticket_ids) > settings.max_tickets_per_request:
            raise HTTPException(
                status_code=422,
                detail=f"Maksimal {settings.max_tickets_per_request} tiket per request, diterima {len(ticket_ids)}",
            )
        return _pipeline(request).run(ticket_ids, doc_types)

    return app


def _pipeline(request: Request) -> TicketOcrPipeline:
    return request.app.state.pipeline


def _api_key_dependency(settings: Settings):
    header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(api_key: str | None = Security(header)) -> None:
        if settings.api_key and not secrets.compare_digest(api_key or "", settings.api_key):
            raise HTTPException(status_code=401, detail="X-API-Key tidak valid")

    return require_api_key


def _add_docs_routes(app: FastAPI) -> None:
    app.mount("/static/swagger-ui", StaticFiles(directory=SWAGGER_UI_DIR), name="swagger-ui")

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui/swagger-ui.css",
            swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    async def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
