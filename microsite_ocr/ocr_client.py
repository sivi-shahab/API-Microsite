import requests

from .config import Settings
from .documents import DocumentType, DownloadedFile
from .images import detect_image_type


class OcrError(RuntimeError):
    pass


class OcrClient:
    """Klien OCR API (Qwen2.5-VL) untuk endpoint /extract/ktp dan /extract/npwp."""

    def __init__(self, base_url: str, timeout_seconds: float, session: requests.Session | None = None):
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls, settings: Settings) -> "OcrClient":
        return cls(settings.ocr_base_url, settings.ocr_timeout_seconds)

    def is_ready(self, timeout_seconds: float) -> bool:
        try:
            response = self._session.get(f"{self._base_url}/health", timeout=timeout_seconds)
            return response.ok and response.json().get("status") == "ok"
        except (requests.RequestException, ValueError):
            return False

    def extract(self, doc_type: DocumentType, file: DownloadedFile, name: str) -> dict:
        if not doc_type.supports_ocr:
            raise ValueError(f"Dokumen {doc_type.value} tidak didukung OCR")

        content_type, extension = detect_image_type(file.content)
        response = self._session.post(
            f"{self._base_url}/extract/{doc_type.value}",
            files={"file": (f"{name}.{extension}", file.content, content_type)},
            timeout=self._timeout,
        )
        if not response.ok:
            raise OcrError(f"OCR {doc_type.value} gagal: HTTP {response.status_code} {response.text[:200]}")
        return response.json()["data"]
