"""Buat Postman Collection v2.1 (bisa di-import juga ke Insomnia) dari contoh di `openapi_examples.py`.

Contoh:
    python -m microsite_ocr.postman > microsite_ocr.postman_collection.json
"""
import json

from .openapi_examples import (
    HEALTH_RESPONSES,
    TICKET_BY_TYPE_RESPONSES,
    TICKET_RESPONSES,
    TICKETS_BY_TYPE_RESPONSES,
    TICKETS_REQUEST_EXAMPLES,
    TICKETS_RESPONSES,
)

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
NO_AUTH = {"type": "noauth"}
STATUS_TEXT = {200: "OK", 401: "Unauthorized", 422: "Unprocessable Entity", 502: "Bad Gateway"}

TWO_TICKETS = TICKETS_REQUEST_EXAMPLES["dua_tiket"]["value"]


def _request(method: str, path: str, body: dict | None = None, auth: dict | None = None) -> dict:
    request = {
        "method": method,
        "header": [],
        "url": {"raw": "{{base_url}}" + path, "host": ["{{base_url}}"], "path": path.strip("/").split("/")},
    }
    if body is not None:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    if auth is not None:
        request["auth"] = auth
    return request


def _saved_responses(request: dict, responses: dict, pick: dict[int, list[str]] | None) -> list[dict]:
    """Contoh response tersimpan (tab Examples di Postman); `pick` memilih status code dan contohnya."""
    saved = []
    for code, response in responses.items():
        examples = response["content"]["application/json"]["examples"]
        if pick is not None and code not in pick:
            continue
        for key in examples if pick is None else pick[code]:
            example = examples[key]
            saved.append({
                "name": f"{code} {example.get('summary', response['description'])}",
                "originalRequest": request,
                "status": STATUS_TEXT[code],
                "code": code,
                "_postman_previewlanguage": "json",
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "body": json.dumps(example["value"], indent=2, ensure_ascii=False),
            })
    return saved


def _item(name: str, description: str, request: dict, responses: dict, pick: dict[int, list[str]] | None = None) -> dict:
    saved = _saved_responses(request, responses, pick)
    # Insomnia tidak mengimpor saved response, jadi contoh pertama juga ditaruh di deskripsi (tab Docs).
    first = saved[0]
    description += f"\n\nContoh response ({first['name']}):\n\n```json\n{first['body']}\n```"
    return {"name": name, "request": {**request, "description": description}, "response": saved}


def _folder(name: str, items: list[dict], description: str = "") -> dict:
    return {"name": name, "description": description, "item": items}


def build_collection() -> dict:
    by_type_one = "Hanya dokumen jenis ini yang di-download dan di-OCR; jenis lain dicatat di `skipped`."
    by_type_many = "Sama dengan `POST /tickets/ocr`, tetapi hanya satu jenis dokumen; jenis lain dicatat di `skipped`."
    single = [
        _item("OCR KTP + NPWP", "OCR semua KTP/NPWP dalam satu tiket.",
              _request("GET", "/tickets/{{ticket_id}}/ocr"), TICKET_RESPONSES),
        _item("OCR KTP saja", by_type_one,
              _request("GET", "/tickets/{{ticket_id}}/ocr/ktp"), TICKET_BY_TYPE_RESPONSES,
              pick={200: ["ktp"], 401: ["api_key"], 422: ["ticket_id"], 502: ["dms"]}),
        _item("OCR NPWP saja", by_type_one,
              _request("GET", "/tickets/{{ticket_id}}/ocr/npwp"), TICKET_BY_TYPE_RESPONSES,
              pick={200: ["npwp_kosong", "npwp"], 401: ["api_key"], 422: ["ticket_id"], 502: ["dms"]}),
    ]
    batch = [
        _item("OCR KTP + NPWP", "OCR beberapa tiket. Hasil berurutan sesuai input, tanpa duplikat; "
                                "kegagalan per tiket ditandai di `error`.",
              _request("POST", "/tickets/ocr", TWO_TICKETS), TICKETS_RESPONSES),
        _item("OCR KTP saja", by_type_many,
              _request("POST", "/tickets/ocr/ktp", TWO_TICKETS), TICKETS_BY_TYPE_RESPONSES,
              pick={200: ["ktp"], 401: ["api_key"], 422: ["terlalu_banyak"]}),
        _item("OCR NPWP saja", by_type_many,
              _request("POST", "/tickets/ocr/npwp", TWO_TICKETS), TICKETS_BY_TYPE_RESPONSES,
              pick={200: ["npwp_kosong", "npwp"], 401: ["api_key"], 422: ["terlalu_banyak"]}),
    ]
    errors = [
        _item("401 tanpa API key", "Request tanpa header `X-API-Key`.",
              _request("GET", "/tickets/{{ticket_id}}/ocr/ktp", auth=NO_AUTH), TICKET_BY_TYPE_RESPONSES,
              pick={401: ["api_key"]}),
        _item("422 jenis dokumen salah", "Jenis dokumen selain `ktp`/`npwp`.",
              _request("GET", "/tickets/{{ticket_id}}/ocr/sim"), TICKET_BY_TYPE_RESPONSES,
              pick={422: ["doc_type"]}),
        _item("422 nomor tiket tidak valid", "Nomor tiket harus sesuai pola `[A-Za-z0-9_-]{1,64}`.",
              _request("GET", "/tickets/tiket!/ocr"), TICKET_RESPONSES, pick={422: ["ticket_id"]}),
    ]
    return {
        "info": {
            "name": "Microsite OCR Service",
            "description": "OCR KTP/NPWP dari DMS-Cardsys berdasarkan nomor tiket. Isi variabel collection "
                           "`base_url` dan `api_key` dulu. Contoh response: NIK dan data pribadi disamarkan, "
                           "contoh NPWP masih ilustrasi. Dibuat oleh `python -m microsite_ocr.postman`.",
            "schema": SCHEMA,
        },
        "auth": {"type": "apikey", "apikey": [
            {"key": "key", "value": "X-API-Key", "type": "string"},
            {"key": "value", "value": "{{api_key}}", "type": "string"},
            {"key": "in", "value": "header", "type": "string"},
        ]},
        "variable": [
            {"key": "base_url", "value": "http://localhost:8090"},
            {"key": "api_key", "value": ""},
            {"key": "ticket_id", "value": "081156CqJu"},
        ],
        "item": [
            _folder("System", [_item("Health", "Status DMS dan OCR API. Tidak butuh API key.",
                                     _request("GET", "/health", auth=NO_AUTH), HEALTH_RESPONSES)]),
            _folder("Satu tiket", single, "Nomor tiket diambil dari variabel `ticket_id`."),
            _folder("Beberapa tiket", batch, "Body `{\"ticket_ids\": [...]}`, maksimal `MAX_TICKETS_PER_REQUEST`."),
            _folder("Contoh error", errors),
        ],
    }


def main() -> None:
    print(json.dumps(build_collection(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
