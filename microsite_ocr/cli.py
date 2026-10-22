"""Bagian yang dipakai bersama oleh CLI OCR (`__main__.py`) dan CLI download (`download.py`)."""
import argparse
import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
EXIT_NO_TICKETS = 2


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stderr)


def ticket_argument_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("tickets", nargs="*", help="Nomor tiket (NomorDokumen)")
    parser.add_argument("--file", type=Path, help="File berisi satu nomor tiket per baris")
    return parser


def load_ticket_ids(tickets: list[str], ticket_file: Path | None) -> list[str]:
    """Gabungkan nomor tiket dari argumen dan file (satu per baris), tanpa duplikat, urutan tetap."""
    ticket_ids = list(tickets)
    if ticket_file:
        ticket_ids += [line.strip() for line in ticket_file.read_text().splitlines() if line.strip()]
    return list(dict.fromkeys(ticket_ids))


def ticket_ids_from_args(args: argparse.Namespace) -> list[str] | None:
    """Nomor tiket dari argumen `ticket_argument_parser`; None (dan pesan ke stderr) bila kosong."""
    ticket_ids = load_ticket_ids(args.tickets, args.file)
    if not ticket_ids:
        print("Tidak ada nomor tiket. Isi argumen atau --file.", file=sys.stderr)
        return None
    return ticket_ids
