from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SONGS_DIR = ROOT / "database" / "songs"
BOOK_ORDER = ["hymns", "supplement", "new-songs", "new-poems", "blue-poems"]
BOOK_LABELS = {
    "hymns": "詩歌",
    "supplement": "補充",
    "new-songs": "新歌",
    "new-poems": "新詩",
    "blue-poems": "藍本",
}


def folder_number(path: Path) -> int | None:
    if re.fullmatch(r"\d{4}", path.name):
        return int(path.name)
    if re.fullmatch(r"A\d{3}", path.name):
        return 780000 + int(path.name[1:])
    return None


def display_number(number: int) -> str:
    if number >= 780000:
        return f"附{number - 780000}"
    return str(number)


def song_title(book: str, number: int) -> str:
    folder = f"{number:04d}" if number < 780000 else f"A{number - 780000:03d}"
    path = SONGS_DIR / book / folder / "song.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("title") or "")


def find_missing(book: str, max_gap: int) -> list[tuple[int, int, list[int]]]:
    book_dir = SONGS_DIR / book
    numbers = sorted(
        number
        for child in book_dir.iterdir()
        if child.is_dir() and (number := folder_number(child)) is not None
    )
    missing = []
    for previous, current in zip(numbers, numbers[1:]):
        gap = current - previous
        if 1 < gap <= max_gap:
            missing.append((previous, current, list(range(previous + 1, current))))
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Check missing numeric song folders.")
    parser.add_argument("--max-gap", type=int, default=40, help="Only report gaps up to this size.")
    args = parser.parse_args()

    for book in BOOK_ORDER:
        missing = find_missing(book, args.max_gap)
        label = BOOK_LABELS.get(book, book)
        print(f"{label} ({book})")
        if not missing:
            print("  無缺號")
            continue
        for previous, current, numbers in missing:
            prev_title = song_title(book, previous)
            curr_title = song_title(book, current)
            names = ", ".join(display_number(number) for number in numbers)
            print(
                f"  {display_number(previous)} -> {display_number(current)} 缺: {names}"
                f"  ({prev_title} / {curr_title})"
            )


if __name__ == "__main__":
    main()
