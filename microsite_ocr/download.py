"""Unduh semua dokumen (KTP, NPWP, SELFIE, dll.) per tiket dari DMS-Cardsys, tanpa OCR.

Contoh:
    python -m microsite_ocr.download --file tickets.txt
    python -m microsite_ocr.download 081156CqJu --output-dir downloads
"""
import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from .cli import EXIT_NO_TICKETS, configure_logging, ticket_argument_parser, ticket_ids_from_args
from .config import Settings
from .dms_client import DmsClient
from .documents import DmsDocument, DownloadedFile
from .images import UnsupportedImageError, detect_image_type

logger = logging.getLogger(__name__)

FALLBACK_EXTENSION = "bin"


def file_extension(file: DownloadedFile) -> str:
    try:
        _, extension = detect_image_type(file.content)
    except UnsupportedImageError:
        return FALLBACK_EXTENSION
    return extension


class TicketDownloader:
    """Tiket → search DMS → download semua dokumen ke `<JENIS>_<tiket>[_n].<ext>`."""

    def __init__(self, dms: DmsClient, output_dir: Path):
        self._dms = dms
        self._output_dir = output_dir

    def run(self, ticket_ids: list[str]) -> bool:
        """Kembalikan True bila semua search dan download berhasil."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        all_ok = True
        for ticket_id in ticket_ids:
            all_ok &= self._download_ticket(ticket_id)
        return all_ok

    def _download_ticket(self, ticket_id: str) -> bool:
        try:
            documents = self._dms.search_by_ticket(ticket_id)
        except Exception as exc:
            logger.error("Tiket %s: search gagal: %s", ticket_id, exc)
            return False

        if not documents:
            logger.warning("Tiket %s: tidak ada dokumen di DMS", ticket_id)

        all_ok = True
        seen_per_type: Counter[str] = Counter()
        for document in documents:
            type_name = document.type.name
            seen_per_type[type_name] += 1
            all_ok &= self._download_document(document, seen_per_type[type_name])
        return all_ok

    def _download_document(self, document: DmsDocument, sequence: int) -> bool:
        try:
            file = self._dms.download(document.node_id)
        except Exception as exc:
            logger.error("Tiket %s: download %s gagal: %s", document.ticket_id, document.node_id, exc)
            return False

        path = self._output_path(document, sequence, file)
        path.write_bytes(file.content)
        logger.info("Tiket %s: %s → %s (%d bytes)", document.ticket_id, document.node_id, path, len(file.content))
        return True

    def _output_path(self, document: DmsDocument, sequence: int, file: DownloadedFile) -> Path:
        # Dokumen kedua dengan jenis yang sama diberi akhiran _2, _3, dst.
        suffix = "" if sequence == 1 else f"_{sequence}"
        return self._output_dir / f"{document.type.name}_{document.ticket_id}{suffix}.{file_extension(file)}"


def parse_args() -> argparse.Namespace:
    parser = ticket_argument_parser("Unduh dokumen DMS-Cardsys berdasarkan nomor tiket")
    parser.add_argument("--output-dir", type=Path, default=Path("downloads"), help="Folder tujuan (default: downloads)")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    ticket_ids = ticket_ids_from_args(args)
    if not ticket_ids:
        return EXIT_NO_TICKETS

    downloader = TicketDownloader(DmsClient.from_settings(Settings.from_env()), args.output_dir)
    return 0 if downloader.run(ticket_ids) else 1


if __name__ == "__main__":
    sys.exit(main())
