"""Face matching KTP vs SELFIE per nomor dokumen.

Dipakai bersama oleh `recorder.py` (setiap hit API) dan `backfill_similarity.py` (data lama),
jadi aturan skornya ada di satu tempat:
- setiap pasangan SELFIE × KTP satu nomor dokumen dibandingkan, skor yang dipakai yang tertinggi;
- nomor dokumen yang semua verify-nya gagal tidak diberi skor.
"""
import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import Settings
from .documents import DocumentType
from .face_client import FaceClient

logger = logging.getLogger(__name__)

# (nomor dokumen, jenis dokumen, isi file)
FaceImage = tuple[str, DocumentType, bytes | None]


@dataclass
class TicketFaces:
    selfies: list[bytes] = field(default_factory=list)
    ktps: list[bytes] = field(default_factory=list)

    @property
    def pairs(self) -> list[tuple[bytes, bytes]]:
        return [(selfie, ktp) for selfie in self.selfies for ktp in self.ktps]


def group_faces(images: Iterable[FaceImage]) -> dict[str, TicketFaces]:
    """Kelompokkan foto per nomor dokumen; hanya nomor dokumen yang punya KTP dan SELFIE yang dikembalikan."""
    grouped: dict[str, TicketFaces] = {}
    for ticket_id, doc_type, content in images:
        if not content:
            continue
        faces = grouped.setdefault(ticket_id, TicketFaces())
        if doc_type is DocumentType.KTP:
            faces.ktps.append(content)
        elif doc_type is DocumentType.SELFIE:
            faces.selfies.append(content)
    return {ticket_id: faces for ticket_id, faces in grouped.items() if faces.pairs}


class FaceMatcher:
    def __init__(self, client: FaceClient, max_workers: int):
        self._client = client
        self._max_workers = max_workers

    @classmethod
    def from_settings(cls, settings: Settings) -> "FaceMatcher | None":
        """None bila `FACE_API_KEY` kosong (face matching dimatikan)."""
        client = FaceClient.from_settings(settings)
        return cls(client, settings.max_workers) if client else None

    def best_scores(self, faces: dict[str, TicketFaces]) -> dict[str, float]:
        """Skor tertinggi per nomor dokumen. Nomor dokumen yang semua verify-nya gagal tidak ada di hasil."""
        jobs = [(ticket_id, selfie, ktp) for ticket_id, ticket_faces in faces.items() for selfie, ktp in ticket_faces.pairs]
        if not jobs:
            return {}

        # Pool sendiri (bukan pool OCR): beban CompreFace terpisah dari vLLM.
        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(jobs)), thread_name_prefix="face") as executor:
            results = list(executor.map(lambda job: self._verify(*job), jobs))

        scores: dict[str, float] = {}
        for (ticket_id, _, _), score in zip(jobs, results):
            if score is not None:
                scores[ticket_id] = max(score, scores.get(ticket_id, score))
        return scores

    def _verify(self, ticket_id: str, selfie: bytes, ktp: bytes) -> float | None:
        try:
            score = self._client.verify(source=selfie, target=ktp)
        except Exception as exc:
            logger.error("Tiket %s: face verify gagal: %s", ticket_id, exc)
            return None
        logger.info("Tiket %s: face similarity %.4f", ticket_id, score)
        return score
