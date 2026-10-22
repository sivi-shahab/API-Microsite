import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    dms_base_url: str = "http://10.191.22.16:8688"
    ocr_base_url: str = "http://10.168.105.11:8070"
    dms_timeout_seconds: float = 30.0
    # Satu request OCR ±5–7 detik; beri ruang untuk antrean di vLLM.
    ocr_timeout_seconds: float = 120.0
    max_workers: int = 4
    # Hanya untuk service HTTP (`python -m microsite_ocr.service`).
    host: str = "0.0.0.0"
    port: int = 8090
    # Kosong = tanpa autentikasi. Bila diisi, setiap request wajib mengirim header X-API-Key.
    api_key: str = ""
    max_tickets_per_request: int = 50

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            dms_base_url=os.getenv("DMS_BASE_URL", defaults.dms_base_url).rstrip("/"),
            ocr_base_url=os.getenv("OCR_BASE_URL", defaults.ocr_base_url).rstrip("/"),
            dms_timeout_seconds=float(os.getenv("DMS_TIMEOUT", defaults.dms_timeout_seconds)),
            ocr_timeout_seconds=float(os.getenv("OCR_TIMEOUT", defaults.ocr_timeout_seconds)),
            max_workers=int(os.getenv("MAX_WORKERS", defaults.max_workers)),
            host=os.getenv("HOST", defaults.host),
            port=int(os.getenv("PORT", defaults.port)),
            api_key=os.getenv("SERVICE_API_KEY", defaults.api_key),
            max_tickets_per_request=int(os.getenv("MAX_TICKETS_PER_REQUEST", defaults.max_tickets_per_request)),
        )
