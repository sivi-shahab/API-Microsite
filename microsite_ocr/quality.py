"""Penanda kualitas hasil OCR: field kosong dan NIK yang tidak cocok dengan nama file.

Penanda tidak membuat dokumen gagal; ia hanya menandai hasil yang perlu dicek manual.
Pesan sengaja tidak memuat nilai NIK supaya aman ditulis ke log.
"""
import re
from dataclasses import dataclass

from .documents import DmsDocument, DocumentType

NIK_LENGTH = 16
# Bila lebih dari separuh field kosong, foto kemungkinan buram atau terpotong.
MAX_EMPTY_RATIO = 0.5

REQUIRED_FIELDS = {
    DocumentType.KTP: ("NIK", "NAMA", "TTL", "ALAMAT"),
    DocumentType.NPWP: ("NPWP", "NAMA"),
}

# NIK di nama file: deretan digit panjang di segmen terakhir, mis. `KTP_<NIK>` atau `<prefix>_KTP_<NIK>`.
_FILENAME_NIK = re.compile(r"(?:^|_)(\d{12,})$")


@dataclass(frozen=True)
class QualityWarning:
    code: str
    message: str


def check_quality(document: DmsDocument, data: dict) -> list[QualityWarning]:
    warnings = _check_required_fields(document.type, data) + _check_mostly_empty(data)
    if document.type is DocumentType.KTP:
        warnings += _check_nik_against_filename(document.filename, data.get("NIK", ""))
    return warnings


def _check_required_fields(doc_type: DocumentType, data: dict) -> list[QualityWarning]:
    missing = [name for name in REQUIRED_FIELDS.get(doc_type, ()) if not data.get(name)]
    if not missing:
        return []
    return [QualityWarning("required_field_empty", f"Field wajib kosong: {', '.join(missing)}")]


def _check_mostly_empty(data: dict) -> list[QualityWarning]:
    empty_count = sum(1 for value in data.values() if not value)
    if not data or empty_count / len(data) <= MAX_EMPTY_RATIO:
        return []
    return [QualityWarning(
        "mostly_empty",
        f"{empty_count} dari {len(data)} field kosong; kemungkinan foto buram atau terpotong",
    )]


def _check_nik_against_filename(filename: str, ocr_nik: str) -> list[QualityWarning]:
    match = _FILENAME_NIK.search(filename)
    if not match:
        return []

    filename_nik = match.group(1)
    if len(filename_nik) != NIK_LENGTH:
        return [QualityWarning(
            "filename_nik_invalid",
            f"NIK di nama file {len(filename_nik)} digit, seharusnya {NIK_LENGTH}; tidak bisa dibandingkan",
        )]

    if ocr_nik and ocr_nik != filename_nik:
        positions = [str(i + 1) for i, (a, b) in enumerate(zip(ocr_nik, filename_nik)) if a != b]
        detail = f"beda di digit ke-{', '.join(positions)}" if len(ocr_nik) == NIK_LENGTH else "panjang berbeda"
        return [QualityWarning("nik_mismatch", f"NIK hasil OCR berbeda dari NIK di nama file ({detail})")]
    return []
