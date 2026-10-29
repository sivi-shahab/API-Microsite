import os
from dataclasses import dataclass, field


class ConfigError(ValueError):
    """Nilai environment variable tidak valid."""


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_url(name: str, default: str) -> str:
    value = _env_str(name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ConfigError(f"{name} harus diawali http:// atau https://, diterima {value!r}")
    return value


def _env_number(name: str, default: float, cast: type, minimum: float) -> float:
    raw = _env_str(name, str(default))
    try:
        value = cast(raw)
    except ValueError:
        raise ConfigError(f"{name} harus berupa {cast.__name__}, diterima {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} minimal {minimum}, diterima {value}")
    return value


@dataclass(frozen=True)
class Settings:
    dms_base_url: str = "http://10.191.22.16:8688"
    ocr_base_url: str = "http://10.168.105.11:8070"
    # Header X-API-Key ke OCR API (salah satu nilai API_KEYS di /data/ocr-qwen/.env).
    # Field rahasia memakai repr=False supaya tidak ikut tercetak bila Settings di-log.
    ocr_api_key: str = field(default="", repr=False)
    dms_timeout_seconds: float = 30.0
    # Satu request OCR ±5–7 detik; beri ruang untuk antrean di vLLM.
    ocr_timeout_seconds: float = 120.0
    max_workers: int = 4
    # Hanya untuk service HTTP (`python -m microsite_ocr.service`).
    host: str = "0.0.0.0"
    port: int = 8090
    # Kosong = tanpa autentikasi. Bila diisi, setiap request wajib mengirim header X-API-Key.
    api_key: str = field(default="", repr=False)
    max_tickets_per_request: int = 50
    # PostgreSQL untuk menyimpan setiap dokumen yang diproses. Kosong = tidak disimpan.
    database_url: str = field(default="", repr=False)
    # Face Verification Service (CompreFace) untuk similarity KTP vs SELFIE. API key kosong = tidak dihitung.
    face_base_url: str = "http://localhost:8000"
    face_api_key: str = field(default="", repr=False)
    face_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            dms_base_url=_env_url("DMS_BASE_URL", defaults.dms_base_url),
            ocr_base_url=_env_url("OCR_BASE_URL", defaults.ocr_base_url),
            ocr_api_key=_env_str("OCR_API_KEY", defaults.ocr_api_key),
            dms_timeout_seconds=_env_number("DMS_TIMEOUT", defaults.dms_timeout_seconds, float, 1),
            ocr_timeout_seconds=_env_number("OCR_TIMEOUT", defaults.ocr_timeout_seconds, float, 1),
            max_workers=_env_number("MAX_WORKERS", defaults.max_workers, int, 1),
            host=_env_str("HOST", defaults.host),
            port=_env_number("PORT", defaults.port, int, 1),
            api_key=_env_str("SERVICE_API_KEY", defaults.api_key),
            max_tickets_per_request=_env_number("MAX_TICKETS_PER_REQUEST", defaults.max_tickets_per_request, int, 1),
            database_url=_env_str("DATABASE_URL", defaults.database_url),
            face_base_url=_env_url("FACE_BASE_URL", defaults.face_base_url),
            face_api_key=_env_str("FACE_API_KEY", defaults.face_api_key),
            face_timeout_seconds=_env_number("FACE_TIMEOUT", defaults.face_timeout_seconds, float, 1),
        )
