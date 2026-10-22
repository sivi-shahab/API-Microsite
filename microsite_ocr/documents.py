from dataclasses import dataclass
from enum import Enum


class DocumentType(str, Enum):
    KTP = "ktp"
    NPWP = "npwp"
    SELFIE = "selfie"
    UNKNOWN = "unknown"

    @property
    def supports_ocr(self) -> bool:
        return self in (DocumentType.KTP, DocumentType.NPWP)


def classify_filename(filename: str) -> DocumentType:
    """Tentukan jenis dokumen dari nama file DMS.

    Nama file memakai dua pola: `KTP_<NIK>` dan `<prefix>_KTP_<NIK>`,
    jadi jenisnya dicari di setiap segmen yang dipisah `_`.
    """
    segments = {segment.upper() for segment in filename.split("_")}
    for doc_type in (DocumentType.KTP, DocumentType.NPWP, DocumentType.SELFIE):
        if doc_type.name in segments:
            return doc_type
    return DocumentType.UNKNOWN


@dataclass(frozen=True)
class DmsDocument:
    ticket_id: str
    node_id: str
    filename: str
    created_at: str

    @property
    def type(self) -> DocumentType:
        return classify_filename(self.filename)


@dataclass(frozen=True)
class DownloadedFile:
    content: bytes
    content_type: str


@dataclass(frozen=True)
class ProcessedDocument:
    """Satu dokumen yang sudah diproses dalam satu hit, siap direkam (lihat `recorder.py`)."""

    document: DmsDocument
    # None bila download gagal.
    content: bytes | None
    # Hasil OCR satu dokumen (bentuk `data[]` di response); None untuk SELFIE.
    ocr_result: dict | None
