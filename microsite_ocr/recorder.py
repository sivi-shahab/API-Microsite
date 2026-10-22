"""Rekam dokumen satu hit API ke database, lengkap dengan face similarity bila diaktifkan."""
import logging
from datetime import datetime

from .config import Settings
from .documents import ProcessedDocument
from .face_matching import FaceMatcher, group_faces
from .store import OcrStore

logger = logging.getLogger(__name__)


class HitRecorder:
    """Implementasi `DocumentRecorder` (lihat `pipeline.py`).

    Gagal face matching atau gagal simpan hanya dicatat di log, supaya hasil OCR tetap dikembalikan.
    """

    def __init__(self, store: OcrStore, matcher: FaceMatcher | None = None):
        self._store = store
        self._matcher = matcher

    @classmethod
    def from_settings(cls, settings: Settings) -> "HitRecorder | None":
        """None bila `DATABASE_URL` kosong; face matching ikut aktif bila `FACE_API_KEY` diisi."""
        store = OcrStore.from_settings(settings)
        return cls(store, FaceMatcher.from_settings(settings)) if store else None

    @property
    def face_matching_enabled(self) -> bool:
        return self._matcher is not None

    def record(self, hit_at: datetime, documents: list[ProcessedDocument]) -> None:
        try:
            self._store.save(hit_at, documents, similarities=self._similarities(documents))
        except Exception as exc:
            logger.error("Simpan %d dokumen ke database gagal: %s", len(documents), exc)

    def _similarities(self, documents: list[ProcessedDocument]) -> dict[str, float]:
        if not self._matcher:
            return {}
        faces = group_faces((item.document.ticket_id, item.document.type, item.content) for item in documents)
        return self._matcher.best_scores(faces)
