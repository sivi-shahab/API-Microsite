"""Contoh:
    python -m microsite_ocr 081156CqJu 020803XGC9
    python -m microsite_ocr --file tickets.txt --output hasil_ocr.json
    python -m microsite_ocr --type npwp --file tickets.txt
"""
import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from .cli import EXIT_NO_TICKETS, configure_logging, ticket_argument_parser, ticket_ids_from_args
from .config import Settings
from .dms_client import DmsClient
from .documents import DocumentType
from .face_client import FaceClient
from .ocr_client import OcrClient
from .pipeline import TicketOcrPipeline, TicketResult
from .store import OcrStore


def parse_args() -> argparse.Namespace:
    parser = ticket_argument_parser("OCR KTP/NPWP dari DMS-Cardsys berdasarkan nomor tiket")
    parser.add_argument("--output", type=Path, help="Simpan hasil ke file JSON (default: stdout)")
    parser.add_argument(
        "--type",
        choices=[t.value for t in DocumentType if t.supports_ocr],
        help="Hanya OCR dokumen jenis ini; jenis lain dicatat di `skipped` (default: KTP dan NPWP)",
    )
    return parser.parse_args()


def write_results(results: list[TicketResult], output: Path | None) -> None:
    content = json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False)
    if output:
        output.write_text(content)
        logging.info("Hasil disimpan ke %s", output)
    else:
        print(content)


def main() -> int:
    configure_logging()
    args = parse_args()
    ticket_ids = ticket_ids_from_args(args)
    if not ticket_ids:
        return EXIT_NO_TICKETS

    settings = Settings.from_env()
    with TicketOcrPipeline(
        dms=DmsClient.from_settings(settings),
        ocr=OcrClient.from_settings(settings),
        max_workers=settings.max_workers,
        store=OcrStore.from_settings(settings),
        face=FaceClient.from_settings(settings),
    ) as pipeline:
        results = pipeline.run(ticket_ids, doc_types=[DocumentType(args.type)] if args.type else None)

    write_results(results, args.output)
    return 1 if any(result.has_error for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
