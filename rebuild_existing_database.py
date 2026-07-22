from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
DATABASE = ROOT / "database"
SONGS = DATABASE / "songs"
SEARCH_SHARD_SIZE = 50

BOOK_LABELS = {
    "hymns": "詩歌",
    "supplement": "補充",
    "new-songs": "新歌",
    "new-poems": "新詩",
    "blue-poems": "藍本",
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def display_sort_key(value) -> tuple[int, int]:
    if isinstance(value, int):
        return (0, value)
    text = str(value)
    if text.startswith("附"):
        return (1, int(text.replace("附", "") or 0))
    return (0, int(text) if text.isdigit() else 0)


def lyrics_text_from_json(path: Path) -> tuple[str, list[str]]:
    if not path.exists():
        return "", []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rows = data.get("verses") or data.get("lyrics") or []
    else:
        rows = data
    verses = []
    for item in rows:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            label = item.get("label")
            if not label:
                if item.get("verse_no") is not None:
                    label = f"第{item['verse_no']}節"
                elif item.get("chorus_no") is not None:
                    label = "副歌"
            text = str(item.get("lyrics") or item.get("text") or "").strip()
            if label and text:
                text = f"{label}: {text}"
        else:
            text = ""
        if text:
            verses.append(text)
    return "\n".join(verses), verses


def rebuild_book(book: str) -> None:
    records = []
    for song_path in sorted((SONGS / book).glob("*/song.json")):
        record = json.loads(song_path.read_text(encoding="utf-8"))
        original = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        lyric_text, lyric_verses = lyrics_text_from_json(song_path.parent / "lyrics.json")
        if lyric_text:
            record["lyricText"] = lyric_text
            record["lyricVerses"] = lyric_verses
            record["text"] = lyric_text
        if json.dumps(record, ensure_ascii=False, separators=(",", ":")) != original:
            write_json(song_path, record)
        records.append((record, song_path))

    records.sort(key=lambda item: display_sort_key(item[0]["number"]))
    public_songs = []
    for record, song_path in records:
        images = record.get("images") or ([record["image"]] if record.get("image") else [])
        public_songs.append(
            {
                "id": record["id"],
                "collection": record["collection"],
                "number": record["number"],
                "title": record["title"],
                "image": images[0] if images else "",
                "data": song_path.relative_to(ROOT).as_posix(),
            }
        )

    shard_paths = []
    search_records = [record for record, _ in records]
    for shard_number, start in enumerate(range(0, len(search_records), SEARCH_SHARD_SIZE), 1):
        path = DATABASE / "search" / book / f"part-{shard_number:02d}.json"
        write_json(path, search_records[start : start + SEARCH_SHARD_SIZE])
        shard_paths.append(path.relative_to(ROOT).as_posix())

    write_json(
        DATABASE / "indexes" / f"{book}.json",
        {"collection": book, "label": BOOK_LABELS[book], "songs": public_songs, "searchFiles": shard_paths},
    )


def main() -> None:
    for book in BOOK_LABELS:
        if (SONGS / book).exists():
            rebuild_book(book)


if __name__ == "__main__":
    main()
