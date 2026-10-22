"""Isi `face_similarity` untuk data lama di tabel `ocr_document`, dari foto base64 yang sudah tersimpan.

Tidak memanggil DMS maupun OCR. Aturan skor sama dengan saat hit API (lihat `face_matching.py`).

Contoh:
    python -m microsite_ocr.backfill_similarity --dry-run
    python -m microsite_ocr.backfill_similarity
    python -m microsite_ocr.backfill_similarity 081156CqJu --rescore
"""
import argparse
import logging
import sys

from .cli import configure_logging, load_ticket_ids, ticket_argument_parser
from .config import Settings
from .face_matching import FaceMatcher, group_faces
from .store import OcrStore

logger = logging.getLogger(__name__)

EXIT_CONFIG_ERROR = 2
DEFAULT_BATCH_SIZE = 20


def parse_args() -> argparse.Namespace:
    parser = ticket_argument_parser(
        "Hitung face similarity KTP vs SELFIE untuk data lama di database. "
        "Tanpa nomor tiket: semua nomor dokumen yang skornya masih NULL."
    )
    parser.add_argument("--rescore", action="store_true", help="Hitung ulang juga nomor dokumen yang sudah punya skor")
    parser.add_argument("--limit", type=int, help="Maksimal jumlah nomor dokumen yang diproses")
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Jumlah nomor dokumen yang fotonya dimuat sekaligus (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Tampilkan nomor dokumen yang akan diproses, tanpa verify")
    return parser.parse_args()


def backfill(store: OcrStore, matcher: FaceMatcher, ticket_ids: list[str], batch_size: int) -> list[str]:
    """Hitung dan simpan skor per batch; kembalikan nomor dokumen yang gagal (semua verify-nya gagal)."""
    failed = []
    for start in range(0, len(ticket_ids), batch_size):
        batch = ticket_ids[start:start + batch_size]
        scores = matcher.best_scores(group_faces(store.face_images(batch)))
        store.set_similarities(scores)
        failed += [ticket_id for ticket_id in batch if ticket_id not in scores]
        logger.info("%d/%d nomor dokumen diproses", min(start + batch_size, len(ticket_ids)), len(ticket_ids))
    return failed


def main() -> int:
    configure_logging()
    args = parse_args()
    settings = Settings.from_env()

    store = OcrStore.from_settings(settings)
    if not store:
        print("DATABASE_URL kosong.", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    pending = store.pending_tickets(load_ticket_ids(args.tickets, args.file), rescore=args.rescore, limit=args.limit)
    logger.info("%d nomor dokumen perlu dihitung", len(pending))
    if args.dry_run:
        print("\n".join(pending))
        return 0

    matcher = FaceMatcher.from_settings(settings)
    if not matcher:
        print("FACE_API_KEY kosong.", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    failed = backfill(store, matcher, pending, args.batch_size)
    logger.info("Selesai: %d berhasil, %d gagal", len(pending) - len(failed), len(failed))
    if failed:
        logger.warning("Nomor dokumen gagal (skor tidak diubah): %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
