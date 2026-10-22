import logging
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .dms_client import DmsClient
from .documents import DmsDocument, DocumentType
from .ocr_client import OcrClient
from .quality import QualityWarning, check_quality

logger = logging.getLogger(__name__)


@dataclass
class DocumentResult:
    node_id: str
    filename: str
    document_type: str
    created_at: str
    data: dict | None = None
    warnings: list[QualityWarning] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def for_document(cls, document: DmsDocument) -> "DocumentResult":
        return cls(
            node_id=document.node_id,
            filename=document.filename,
            document_type=document.type.value,
            created_at=document.created_at,
        )


@dataclass
class TicketResult:
    ticket_id: str
    data: list[DocumentResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def has_error(self) -> bool:
        return bool(self.error) or any(document.error for document in self.data)


OcrJob = tuple[TicketResult, DmsDocument]


class TicketOcrPipeline:
    """Tiket → search DMS → download KTP/NPWP → OCR.

    Thread pool OCR dipakai bersama oleh semua pemanggil `run`, jadi di service HTTP
    jumlah request OCR serentak tetap dibatasi `max_workers` walau ada banyak request masuk.
    """

    def __init__(self, dms: DmsClient, ocr: OcrClient, max_workers: int):
        self._dms = dms
        self._ocr = ocr
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ocr")

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def __enter__(self) -> "TicketOcrPipeline":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def run(self, ticket_ids: list[str], doc_types: Collection[DocumentType] | None = None) -> list[TicketResult]:
        """OCR dokumen tiket; `doc_types` membatasi jenis yang di-OCR (default: semua yang `supports_ocr`)."""
        results = [TicketResult(ticket_id) for ticket_id in ticket_ids]
        jobs = [job for result in results for job in self._collect_jobs(result, doc_types)]

        # OCR dijalankan paralel; vLLM mem-batch request bersamaan.
        processed = self._executor.map(lambda job: self._process_document(job[1]), jobs)
        for (result, _), document_result in zip(jobs, processed):
            result.data.append(document_result)

        return results

    def _collect_jobs(self, result: TicketResult, doc_types: Collection[DocumentType] | None) -> list[OcrJob]:
        """Search dokumen tiket; jenis yang diminta jadi job OCR, sisanya dicatat di `skipped`."""
        try:
            documents = self._dms.search_by_ticket(result.ticket_id)
        except Exception as exc:
            logger.error("Tiket %s: search gagal: %s", result.ticket_id, exc)
            result.error = str(exc)
            return []

        # Tiket tanpa dokumen bukan error; hasilnya cukup `data: []`.
        if not documents:
            logger.warning("Tiket %s: tidak ada dokumen di DMS", result.ticket_id)

        jobs = []
        for document in documents:
            if document.type.supports_ocr and (doc_types is None or document.type in doc_types):
                jobs.append((result, document))
            else:
                result.skipped.append(f"{document.type.value}: {document.node_id}")
        return jobs

    def _process_document(self, document: DmsDocument) -> DocumentResult:
        result = DocumentResult.for_document(document)
        label = f"Tiket {document.ticket_id}: {document.type.value} {document.node_id}"
        try:
            file = self._dms.download(document.node_id)
            result.data = self._ocr.extract(document.type, file, name=document.node_id)
            result.warnings = check_quality(document, result.data)
        except Exception as exc:
            logger.error("%s gagal: %s", label, exc)
            result.error = str(exc)
            return result

        logger.info("%s selesai", label)
        for warning in result.warnings:
            logger.warning("%s: %s", label, warning.message)
        return result
