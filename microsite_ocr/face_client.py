import requests

from .config import Settings
from .images import detect_image_type


class FaceError(RuntimeError):
    pass


class FaceClient:
    """Klien Face Verification Service (CompreFace) untuk endpoint /api/v1/verification/verify."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float, session: requests.Session | None = None):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls, settings: Settings) -> "FaceClient | None":
        """None bila `FACE_API_KEY` kosong (face matching dimatikan)."""
        if not settings.face_api_key:
            return None
        return cls(settings.face_base_url, settings.face_api_key, settings.face_timeout_seconds)

    def verify(self, source: bytes, target: bytes) -> float:
        """Similarity wajah `source` (SELFIE) terhadap wajah di `target` (KTP), 0–1; skor tertinggi bila ada beberapa wajah."""
        response = self._session.post(
            f"{self._base_url}/api/v1/verification/verify",
            headers={"x-api-key": self._api_key},
            files={"source_image": _image_part("source", source), "target_image": _image_part("target", target)},
            timeout=self._timeout,
        )
        if not response.ok:
            raise FaceError(f"HTTP {response.status_code} {response.text[:200]}")

        matches = [match for result in response.json().get("result", []) for match in result.get("face_matches", [])]
        if not matches:
            raise FaceError("tidak ada wajah yang cocok di gambar target")
        return max(match["similarity"] for match in matches)


def _image_part(name: str, content: bytes) -> tuple[str, bytes, str]:
    # CompreFace memvalidasi format dari nama file, jadi ekstensinya diambil dari isi file.
    content_type, extension = detect_image_type(content)
    return f"{name}.{extension}", content, content_type
