"""Akses PostgreSQL untuk tabel `ocr_document` (schema di db/init/). Semua SQL ada di sini."""
import base64
import logging
from collections.abc import Collection
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings
from .documents import DocumentType, ProcessedDocument

logger = logging.getLogger(__name__)

# Format `createDate` dari search DMS, mis. "2026-10-21 11:07:53".
DMS_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_INSERT = """
    INSERT INTO ocr_document (hit_at, nomor_dokumen, create_date, file_type, node_id, file_base64, ocr_result)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

# Fungsi di schema: isi skor yang sama ke semua KTP & SELFIE satu nomor dokumen (semua hit).
_SET_SIMILARITY = "SELECT set_face_similarity(%s::varchar, %s::numeric)"

# Nomor dokumen yang punya foto KTP dan SELFIE; tanpa `rescore` hanya yang masih ada skor NULL.
_PENDING_TICKETS = """
    SELECT nomor_dokumen
      FROM ocr_document
     WHERE file_type IN ('ktp', 'selfie')
       AND (%(ticket_ids)s::text[] IS NULL OR nomor_dokumen = ANY(%(ticket_ids)s))
     GROUP BY nomor_dokumen
    HAVING bool_or(file_type = 'ktp' AND file_base64 IS NOT NULL)
       AND bool_or(file_type = 'selfie' AND file_base64 IS NOT NULL)
       AND (%(rescore)s OR bool_or(face_similarity IS NULL))
     ORDER BY min(hit_at)
     LIMIT %(limit)s
"""

# Satu foto per node_id (hit terbaru); node yang sama di beberapa hit isinya sama.
_FACE_IMAGES = """
    SELECT DISTINCT ON (nomor_dokumen, node_id) nomor_dokumen, file_type, file_base64
      FROM ocr_document
     WHERE nomor_dokumen = ANY(%s)
       AND file_type IN ('ktp', 'selfie')
       AND file_base64 IS NOT NULL
     ORDER BY nomor_dokumen, node_id, hit_at DESC
"""


class OcrStore:
    def __init__(self, database_url: str):
        self._database_url = database_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "OcrStore | None":
        """None bila `DATABASE_URL` kosong (penyimpanan dimatikan)."""
        return cls(settings.database_url) if settings.database_url else None

    def save(self, hit_at: datetime, documents: list[ProcessedDocument], similarities: dict[str, float]) -> None:
        """Simpan dokumen satu hit, lalu terapkan skor similarity per nomor dokumen (satu transaksi)."""
        rows = [_to_row(hit_at, item) for item in documents if item.document.type is not DocumentType.UNKNOWN]
        if not rows:
            return
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            cur.executemany(_INSERT, rows)
            _apply_similarities(cur, similarities)
        logger.info("%d dokumen disimpan ke database", len(rows))

    def set_similarities(self, similarities: dict[str, float]) -> None:
        if not similarities:
            return
        with psycopg.connect(self._database_url) as conn, conn.cursor() as cur:
            _apply_similarities(cur, similarities)

    def pending_tickets(
        self, ticket_ids: Collection[str] | None = None, rescore: bool = False, limit: int | None = None
    ) -> list[str]:
        """Nomor dokumen yang bisa dihitung similarity-nya, urut dari hit paling lama."""
        params = {"ticket_ids": list(ticket_ids) if ticket_ids else None, "rescore": rescore, "limit": limit}
        with psycopg.connect(self._database_url) as conn:
            return [ticket_id for (ticket_id,) in conn.execute(_PENDING_TICKETS, params)]

    def face_images(self, ticket_ids: Collection[str]) -> list[tuple[str, DocumentType, bytes]]:
        """Foto KTP & SELFIE nomor dokumen ini sebagai (nomor dokumen, jenis, isi file)."""
        with psycopg.connect(self._database_url) as conn:
            rows = conn.execute(_FACE_IMAGES, (list(ticket_ids),)).fetchall()
        return [(ticket_id, DocumentType(file_type), base64.b64decode(content)) for ticket_id, file_type, content in rows]


def _apply_similarities(cur: psycopg.Cursor, similarities: dict[str, float]) -> None:
    for ticket_id, score in similarities.items():
        cur.execute(_SET_SIMILARITY, (ticket_id, score))


def _to_row(hit_at: datetime, item: ProcessedDocument) -> tuple:
    document = item.document
    return (
        hit_at,
        document.ticket_id,
        _parse_dms_date(document.created_at),
        document.type.value,
        document.node_id,
        base64.b64encode(item.content).decode("ascii") if item.content is not None else None,
        Jsonb(item.ocr_result) if item.ocr_result is not None else None,
    )


def _parse_dms_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, DMS_DATE_FORMAT)
    except ValueError:
        logger.warning("createDate DMS tidak dikenali: %r", value)
        return None
