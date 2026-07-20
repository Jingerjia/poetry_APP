"""Build a small-index, fully offline database suitable for an Android APK.

Output layout:
  database/indexes/<book>.json       lightweight song lists for the home page
  database/search/<book>/part-*.json search shards (50 songs per file)
  database/songs/<book>/<number>/    that song's JSON and page JPEGs only
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import fitz

ROOT = Path(__file__).parent
PDF_DIR = ROOT / "pdf"
OUT = ROOT / "database"
LEGACY_PAGES = OUT / "pages"
BOOKS = {
    "hymns": ("\u5927\u672c\u8a69\u6b4c.pdf", "\u8a69\u6b4c", 16),
    "supplement": ("\u88dc\u5145\u672c\u8a69\u6b4c_2012\u7248.pdf", "\u88dc\u5145", 4),
    "new-songs": ("\u65b0\u6b4c\u980c\u8a60.pdf", "\u65b0\u6b4c", 1),
    "new-poems": ("\u65b0\u8a69.pdf", "\u65b0\u8a69", 1),
}
SEARCH_SHARD_SIZE = 50


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r", " ")).strip()


def read_heading(text: str):
    """Return only headings found at a genuine score-page start, never a TOC row."""
    match = re.match(r"\s*(?:[^\n]*\.docx\s+)?(\d{1,4})\s+([^\n]{1,100})", text.replace("\r", " "), re.I)
    if not match or int(match.group(1)) == 0:
        return None
    title = re.split(r"(?:\s+[A-Ga-g][b#]?\s+\d|\s+[A-Ga-g][mM]?(?:aj|in)?\b|\s+\(\u4e00\)|\s+\u4e00[\u3001\u3002\u3001])", match.group(2))[0]
    title = re.sub(r"\s+", " ", title).strip(" .-|")
    return (int(match.group(1)), title) if len(title) > 1 else None


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def legacy_image(book: str, page: int) -> Path:
    return LEGACY_PAGES / book / f"{page:04d}.jpg"


def export_book(key: str, filename: str, label: str, first_score_page: int):
    doc = fitz.open(PDF_DIR / filename)
    starts = []
    for page_index in range(first_score_page, doc.page_count):
        found = read_heading(doc[page_index].get_text("text"))
        if found:
            number, title = found
            # This rejects repeated headers inside multi-page songs. It does not
            # assume that every hundred-number range is complete.
            if not starts or number > starts[-1]["number"]:
                starts.append({"number": number, "title": title, "start": page_index})

    public_songs = []
    search_songs = []
    for pos, item in enumerate(starts):
        end = starts[pos + 1]["start"] - 1 if pos + 1 < len(starts) else doc.page_count - 1
        song_dir = OUT / "songs" / key / f"{item['number']:04d}"
        song_dir.mkdir(parents=True, exist_ok=True)
        images = []
        page_text = []
        for page_index in range(item["start"], end + 1):
            source_image = legacy_image(key, page_index + 1)
            destination = song_dir / f"{page_index - item['start'] + 1:02d}.jpg"
            if source_image.exists():
                shutil.move(str(source_image), str(destination))
            else:
                pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
                pix.save(destination, jpg_quality=82)
            images.append(destination.relative_to(ROOT).as_posix())
            page_text.append(clean(doc[page_index].get_text("text")))
        song_id = f"{key}-{item['number']}"
        record = {"id": song_id, "collection": key, "number": item["number"], "title": item["title"],
                  "images": images, "text": " ".join(page_text)}
        write_json(song_dir / "song.json", record)
        public_songs.append({key: record[key] for key in ("id", "collection", "number", "title")}
                            | {"image": images[0], "data": (song_dir / "song.json").relative_to(ROOT).as_posix()})
        search_songs.append(record)
    doc.close()

    shard_paths = []
    for shard_number, start in enumerate(range(0, len(search_songs), SEARCH_SHARD_SIZE), 1):
        path = OUT / "search" / key / f"part-{shard_number:02d}.json"
        write_json(path, search_songs[start:start + SEARCH_SHARD_SIZE])
        shard_paths.append(path.relative_to(ROOT).as_posix())
    write_json(OUT / "indexes" / f"{key}.json", {"collection": key, "label": label, "songs": public_songs,
                                                      "searchFiles": shard_paths})
    print(f"Built {label}: {len(public_songs)} songs, {len(shard_paths)} search files")


def main():
    OUT.mkdir(exist_ok=True)
    for directory in (OUT / "indexes", OUT / "search", OUT / "songs"):
        if directory.exists():
            shutil.rmtree(directory)
    for key, (filename, label, first_score_page) in BOOKS.items():
        export_book(key, filename, label, first_score_page)
    if LEGACY_PAGES.exists():
        shutil.rmtree(LEGACY_PAGES)
    catalog = OUT / "catalog.json"
    if catalog.exists():
        catalog.unlink()
    write_json(OUT / "manifest.json", {"version": 2, "books": list(BOOKS)})
    print("Offline database complete:", OUT)


if __name__ == "__main__":
    main()
