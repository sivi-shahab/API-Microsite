"""Simpan setiap dokumen yang diproses ke PostgreSQL (tabel `ocr_document`, lihat db/init/)."""
import base64
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings
from .documents import DmsDocument, DocumentType

if TYPE_CHECKING:
    from .pipeline import DocumentResult

logger = logging.getLogger(__name__)

# Format `createDate` dari search DMS, mis. "2026-10-21 11:07:53".
DMS_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_INSERT = """
    INSERT INTO ocr_document (hit_at, nomor_dokumen, create_date, file_type, node_id, file_base64, ocr_result)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


@dataclass(frozen=True)
class StoredDocument:
    document: DmsDocument
    # None bila download gagal.
    content: bytes | None
    # Hasil OCR (`DocumentResult`); None untuk SELFIE.
    ocr_result: "DocumentResult | None"


class OcrStore:
    def __init__(self, database_url: str):
        self._database_url = database_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "OcrStore | None":
        """None bila `DATABASE_URL` kosong (penyimpanan dimatikan)."""
        return cls(settings.database_url) if settings.database_url else None

    def save(self, hit_at: datetime, documents: list[StoredDocument]) -> None:
        rows = [_to_row(hit_at, stored) for stored in documents if stored.document.type is not DocumentType.UNKNOWN]
        if not rows:
            return
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
        logger.info("%d dokumen disimpan ke database", len(rows))


def _to_row(hit_at: datetime, stored: StoredDocument) -> tuple:
    document = stored.document
    return (
        hit_at,
        document.ticket_id,
        _parse_dms_date(document.created_at),
        document.type.value,
        document.node_id,
        base64.b64encode(stored.content).decode("ascii") if stored.content is not None else None,
        Jsonb(asdict(stored.ocr_result)) if stored.ocr_result is not None else None,
    )


def _parse_dms_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, DMS_DATE_FORMAT)
    except ValueError:
        logger.warning("createDate DMS tidak dikenali: %r", value)
        return None
