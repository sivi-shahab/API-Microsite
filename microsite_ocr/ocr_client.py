import base64

import requests

from .config import Settings
from .documents import DocumentType, DownloadedFile
from .images import detect_image_type


class OcrError(RuntimeError):
    pass


class OcrClient:
    """Klien OCR API (Qwen2.5-VL) untuk endpoint /extract/ktp/base64 dan /extract/npwp/base64."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        session: requests.Session | None = None,
    ):
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._session = session or requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key

    @classmethod
    def from_settings(cls, settings: Settings) -> "OcrClient":
        return cls(settings.ocr_base_url, settings.ocr_api_key, settings.ocr_timeout_seconds)

    def is_ready(self, timeout_seconds: float) -> bool:
        try:
            response = self._session.get(f"{self._base_url}/health", timeout=timeout_seconds)
            return response.ok and response.json().get("status") == "ok"
        except (requests.RequestException, ValueError):
            return False

    def extract(self, doc_type: DocumentType, file: DownloadedFile) -> dict:
        if not doc_type.supports_ocr:
            raise ValueError(f"Dokumen {doc_type.value} tidak didukung OCR")

        # Ditolak di sini supaya file non-gambar tidak dikirim; OCR API sendiri tidak butuh content-type.
        detect_image_type(file.content)
        response = self._session.post(
            f"{self._base_url}/extract/{doc_type.value}/base64",
            json={"image": base64.b64encode(file.content).decode("ascii")},
            timeout=self._timeout,
        )
        if not response.ok:
            raise OcrError(f"OCR {doc_type.value} gagal: HTTP {response.status_code} {response.text[:200]}")
        return response.json()["data"]
