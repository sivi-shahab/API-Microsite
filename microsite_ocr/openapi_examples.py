"""Contoh request/response untuk Swagger UI (/docs).

Nilai diambil dari hasil service 21 Oktober 2026 dengan NIK dan data pribadi disamarkan.
Contoh NPWP masih ilustrasi karena belum ada dokumen NPWP di DMS.
"""
from fastapi.openapi.models import Example

_SELFIE_SKIPPED = "selfie: d70e1b19-a316-4e08-9b36-1d9c127e18ae"
_KTP_NODE_ID = "71698764-05ff-45f5-9301-537faec89d96"

_KTP_DOCUMENT = {
    "node_id": _KTP_NODE_ID,
    "filename": "KTP_3172XXXXXXXX0012",
    "document_type": "ktp",
    "created_at": "2026-10-21 11:07:53",
    "data": {
        "NIK": "3172XXXXXXXX0012",
        "NAMA": "NAMA NASABAH",
        "TTL": "KOTA, 01-01-1981",
        "JENIS_KELAMIN": "PEREMPUAN",
        "GOL_DARAH": "O",
        "ALAMAT": "JL. CONTOH NO.15",
        "RT_RW": "005/006",
        "KEL_DESA": "KEBON PALA",
        "KECAMATAN": "MAKASAR",
        "AGAMA": "KRISTEN",
        "STATUS_PERKAWINAN": "KAWIN",
        "PEKERJAAN": "KARYAWAN SWASTA",
        "KEWARGANEGARAAN": "WNI",
        "BERLAKU_HINGGA": "SEUMUR HIDUP",
    },
    "warnings": [],
    "error": None,
}

_KTP_DOCUMENT_BLURRY = {
    "node_id": "999818fc-308c-402e-8ac6-d605fd1d0e51",
    "filename": "020803XGC9_KTP_3578XXXXXXXX0002",
    "document_type": "ktp",
    "created_at": "2026-10-21 10:47:42",
    "data": {
        "NIK": "1578XXXXXXXX0002",
        "NAMA": "",
        "TTL": "KOTA, 27-03-1999",
        "JENIS_KELAMIN": "LAKI-LAKI",
        "GOL_DARAH": "",
        "ALAMAT": "",
        "RT_RW": "000/000",
        "KEL_DESA": "",
        "KECAMATAN": "",
        "AGAMA": "",
        "STATUS_PERKAWINAN": "",
        "PEKERJAAN": "",
        "KEWARGANEGARAAN": "",
        "BERLAKU_HINGGA": "SEUMUR HIDUP",
    },
    "warnings": [
        {"code": "required_field_empty", "message": "Field wajib kosong: NAMA, ALAMAT"},
        {"code": "mostly_empty", "message": "9 dari 14 field kosong; kemungkinan foto buram atau terpotong"},
        {"code": "nik_mismatch",
         "message": "NIK hasil OCR berbeda dari NIK di nama file (beda di digit ke-1, 10, 11)"},
    ],
    "error": None,
}

_NPWP_DOCUMENT = {
    "node_id": "<nodeId>",
    "filename": "NPWP_<...>",
    "document_type": "npwp",
    "created_at": "2026-10-21 11:07:53",
    "data": {
        "NPWP": "XX.XXX.XXX.X-XXX.XXX",
        "NAMA": "NAMA NASABAH",
        "NIK": "3172XXXXXXXX0012",
        "ALAMAT": "JL. CONTOH NO.15",
        "KPP": "KPP PRATAMA ...",
        "TANGGAL_TERDAFTAR": "01-01-2015",
    },
    "warnings": [],
    "error": None,
}

_TICKET_KTP = {"ticket_id": "081156CqJu", "data": [_KTP_DOCUMENT], "skipped": [_SELFIE_SKIPPED], "error": None}
_TICKET_NO_NPWP = {
    "ticket_id": "081156CqJu",
    "data": [],
    "skipped": [_SELFIE_SKIPPED, f"ktp: {_KTP_NODE_ID}"],
    "error": None,
}
_TICKET_NPWP = {"ticket_id": "<tiket>", "data": [_NPWP_DOCUMENT], "skipped": [], "error": None}
_TICKET_BLURRY = {"ticket_id": "020803XGC9", "data": [_KTP_DOCUMENT_BLURRY], "skipped": [], "error": None}
_TICKET_NOT_FOUND = {"ticket_id": "TIDAKADA01", "data": [], "skipped": [], "error": None}
_TICKET_OCR_FAILED = {
    "ticket_id": "081156CqJu",
    "data": [{**_KTP_DOCUMENT, "data": None, "error": "OCR ktp gagal: HTTP 500 ..."}],
    "skipped": [_SELFIE_SKIPPED],
    "error": None,
}


def _json_examples(description: str, examples: dict[str, Example]) -> dict:
    return {"description": description, "content": {"application/json": {"examples": examples}}}


TICKET_ID_EXAMPLES = {
    "ktp": Example(summary="Tiket berisi KTP + SELFIE", value="081156CqJu"),
    "buram": Example(summary="Tiket dengan foto KTP buram (ada warnings)", value="020803XGC9"),
    "tidak_ada": Example(summary="Tiket tidak ditemukan di DMS", value="TIDAKADA01"),
}

TICKETS_REQUEST_EXAMPLES = {
    "dua_tiket": Example(summary="Dua tiket", value={"ticket_ids": ["081156CqJu", "020803XGC9"]}),
    "tidak_ada": Example(
        summary="Salah satu tiket tidak ditemukan",
        value={"ticket_ids": ["081156CqJu", "TIDAKADA01"]},
    ),
}

HEALTH_RESPONSES = {
    200: _json_examples("Status DMS dan OCR API", {
        "ok": Example(summary="Semua siap", value={"status": "ok", "dms_reachable": True, "ocr_ready": True}),
        "degraded": Example(
            summary="OCR API tidak siap",
            value={"status": "degraded", "dms_reachable": True, "ocr_ready": False},
        ),
    }),
}

_ERROR_RESPONSES = {
    401: _json_examples("`X-API-Key` tidak dikirim atau salah", {
        "api_key": Example(value={"detail": "X-API-Key tidak valid"}),
    }),
}

_DOC_TYPE_422 = Example(
    summary="Jenis dokumen selain ktp/npwp",
    value={"detail": [{
        "type": "literal_error",
        "loc": ["path", "doc_type"],
        "msg": "Input should be 'ktp' or 'npwp'",
        "input": "sim",
        "ctx": {"expected": "'ktp' or 'npwp'"},
    }]},
)
_TICKET_ID_422 = Example(
    summary="Nomor tiket tidak sesuai pola",
    value={"detail": [{
        "type": "string_pattern_mismatch",
        "loc": ["path", "ticket_id"],
        "msg": "String should match pattern '^[A-Za-z0-9_-]{1,64}$'",
        "input": "tiket!",
        "ctx": {"pattern": "^[A-Za-z0-9_-]{1,64}$"},
    }]},
)
_TOO_MANY_422 = Example(
    summary="Terlalu banyak tiket",
    value={"detail": "Maksimal 50 tiket per request, diterima 51"},
)
_502 = _json_examples("Search ke DMS gagal", {
    "dms": Example(value={"detail": "Search DMS gagal: <pesan error>"}),
})

TICKET_RESPONSES = {
    200: _json_examples("Hasil OCR satu tiket", {
        "ktp": Example(summary="KTP berhasil di-OCR", value=_TICKET_KTP),
        "warnings": Example(summary="Foto buram: ada warnings", value=_TICKET_BLURRY),
        "ocr_gagal": Example(summary="OCR dokumen gagal (ditandai di data[].error)", value=_TICKET_OCR_FAILED),
        "tidak_ada": Example(summary="Tiket tidak ditemukan", value=_TICKET_NOT_FOUND),
    }),
    **_ERROR_RESPONSES,
    422: _json_examples("Parameter tidak valid", {"ticket_id": _TICKET_ID_422}),
    502: _502,
}

TICKET_BY_TYPE_RESPONSES = {
    200: _json_examples("Hasil OCR satu jenis dokumen", {
        "ktp": Example(summary="/ocr/ktp: KTP berhasil di-OCR", value=_TICKET_KTP),
        "npwp_kosong": Example(summary="/ocr/npwp: tiket tanpa NPWP, KTP masuk skipped", value=_TICKET_NO_NPWP),
        "npwp": Example(summary="/ocr/npwp: NPWP berhasil di-OCR (ilustrasi)", value=_TICKET_NPWP),
    }),
    **_ERROR_RESPONSES,
    422: _json_examples("Parameter tidak valid", {"doc_type": _DOC_TYPE_422, "ticket_id": _TICKET_ID_422}),
    502: _502,
}

TICKETS_RESPONSES = {
    200: _json_examples("Hasil OCR per tiket, urutan sesuai input", {
        "dua_tiket": Example(summary="Dua tiket, satu ada warnings", value=[_TICKET_KTP, _TICKET_BLURRY]),
        "tidak_ada": Example(summary="Salah satu tiket tidak ditemukan", value=[_TICKET_KTP, _TICKET_NOT_FOUND]),
        "search_gagal": Example(
            summary="Search DMS gagal untuk satu tiket (ditandai di error)",
            value=[_TICKET_KTP, {**_TICKET_NOT_FOUND, "ticket_id": "020803XGC9", "error": "<pesan error>"}],
        ),
    }),
    **_ERROR_RESPONSES,
    422: _json_examples("Body tidak valid", {"terlalu_banyak": _TOO_MANY_422}),
}

TICKETS_BY_TYPE_RESPONSES = {
    200: _json_examples("Hasil OCR satu jenis dokumen per tiket", {
        "ktp": Example(summary="/ocr/ktp", value=[_TICKET_KTP, _TICKET_NOT_FOUND]),
        "npwp_kosong": Example(
            summary="/ocr/npwp: tiket tanpa NPWP",
            value=[_TICKET_NO_NPWP, {
                "ticket_id": "020803XGC9",
                "data": [],
                "skipped": ["ktp: 999818fc-308c-402e-8ac6-d605fd1d0e51"],
                "error": None,
            }],
        ),
        "npwp": Example(summary="/ocr/npwp: NPWP berhasil di-OCR (ilustrasi)", value=[_TICKET_NPWP]),
    }),
    **_ERROR_RESPONSES,
    422: _json_examples("Parameter tidak valid", {"doc_type": _DOC_TYPE_422, "terlalu_banyak": _TOO_MANY_422}),
}
