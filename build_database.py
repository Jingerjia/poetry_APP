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
APPENDIX_OFFSET = 780000
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
VERSE_MARKER_RE = re.compile(r"^(?:\(?([一二三四五六七八九十]+|\d{1,2})[)）.、])")
CHORUS_MARKER_RE = re.compile(r"[\(（]?副[)）.、]?")
LYRIC_PUNCT_RE = re.compile(r"[，,。.!！?？、；;]+")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r", " ")).strip()


def clean_lyric_line(text: str) -> str:
    text = re.sub(r"[ㄅ-ㄩ˙ˊˇˋ]+", "", text)
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\u4e00-\u9fff，,。.!！?？、；;－\-()）]+", "", text)


def extract_lyric_rows(page) -> list[str]:
    rows = []
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_text = "".join(
                "".join(char.get("c", "") for char in span.get("chars", []))
                for span in line.get("spans", [])
            )
            if not HAN_RE.search(line_text):
                continue
            x0, y0, x1, y1 = line.get("bbox")
            center_y = (y0 + y1) / 2
            for row in rows:
                if abs(row["y"] - center_y) < 6:
                    row["items"].append((x0, line_text))
                    row["y"] = (row["y"] + center_y) / 2
                    break
            else:
                rows.append({"y": center_y, "items": [(x0, line_text)]})

    lyric_rows = []
    for row in sorted(rows, key=lambda item: item["y"]):
        text = clean_lyric_line("".join(text for _, text in sorted(row["items"])))
        if re.match(r"^\d+", text) or "讚美主" in text:
            continue
        if len(re.sub(r"[^\u4e00-\u9fff]", "", text)) >= 2:
            lyric_rows.append(text)
    return lyric_rows


def rebuild_lyric_verses(page) -> list[str]:
    rows = extract_lyric_rows(page)
    first_marker_index = next(
        (index for index, row in enumerate(rows) if VERSE_MARKER_RE.match(row) or CHORUS_MARKER_RE.match(row)),
        None,
    )
    if first_marker_index is not None:
        rows = rows[first_marker_index:]

    verse_count = 0
    for row in rows:
        if CHORUS_MARKER_RE.search(row):
            break
        if VERSE_MARKER_RE.match(row):
            verse_count += 1
        elif verse_count:
            break
    verse_count = max(1, verse_count)

    verses = ["" for _ in range(verse_count)]
    chorus = ""
    in_chorus = False
    for index, row in enumerate(rows):
        chorus_match = CHORUS_MARKER_RE.search(row)
        if chorus_match:
            before_chorus = row[: chorus_match.start()]
            after_chorus = row[chorus_match.end() :]
            if before_chorus:
                verses[index % verse_count] += VERSE_MARKER_RE.sub("", before_chorus)
            in_chorus = True
            chorus += after_chorus
            continue
        clean_row = VERSE_MARKER_RE.sub("", row)
        if in_chorus:
            chorus += clean_row
        else:
            verses[index % verse_count] += clean_row
    if chorus:
        verses.append(chorus)
    return [verse for verse in verses if HAN_RE.search(verse)]


def format_lyric_verse(verse: str) -> str:
    parts = []
    for part in LYRIC_PUNCT_RE.split(verse):
        text = re.sub(r"[^\u4e00-\u9fff]", "", part)
        if text:
            parts.append(text)

    merged = []
    pending = ""
    for part in parts:
        if not pending:
            pending = part
        elif len(pending) < 4:
            pending += part
        else:
            merged.append(pending)
            pending = part
    if pending:
        merged.append(pending)
    return " ".join(merged)


def format_lyric_text(verses: list[str]) -> str:
    return "\n".join(formatted for verse in verses if (formatted := format_lyric_verse(verse)))


def read_heading(text: str):
    """Return only headings found at a genuine score-page start, never a TOC row."""
    match = re.match(
        r"\s*(?:[^\n]*\.docx\s+)?(?:(\d{1,4})|\u9644\s*(\d{1,2}))\s+([^\n]{1,100})",
        text.replace("\r", " "),
        re.I,
    )
    if not match:
        return None
    if match.group(1):
        number = int(match.group(1))
        sort_key = number
    else:
        number = f"\u9644{int(match.group(2))}"
        sort_key = APPENDIX_OFFSET + int(match.group(2))
    if number == 0:
        return None
    title = re.split(
        r"(?:\s+[A-Ga-g][b#]?\s+\d|\s+[A-Ga-g][mM]?(?:aj|in)?\b|\s+\(\u4e00\)|\s+\u4e00[\u3001\u3002\u3001])",
        match.group(3),
    )[0]
    title = re.sub(r"\s+", " ", title).strip(" .-|")
    return (number, title, sort_key) if len(title) > 1 else None


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def legacy_image(book: str, page: int) -> Path:
    return LEGACY_PAGES / book / f"{page:04d}.jpg"


def number_folder(number) -> str:
    if isinstance(number, int):
        return f"{number:04d}"
    return f"A{int(str(number).replace(chr(0x9644), '')):03d}"


def export_book(key: str, filename: str, label: str, first_score_page: int):
    doc = fitz.open(PDF_DIR / filename)
    starts = []
    for page_index in range(first_score_page, doc.page_count):
        found = read_heading(doc[page_index].get_text("text"))
        if found:
            number, title, sort_key = found
            # This rejects repeated headers inside multi-page songs. It does not
            # assume that every hundred-number range is complete.
            if not starts or sort_key > starts[-1]["sortKey"]:
                starts.append({"number": number, "title": title, "sortKey": sort_key, "start": page_index})

    public_songs = []
    search_songs = []
    for pos, item in enumerate(starts):
        end = starts[pos + 1]["start"] - 1 if pos + 1 < len(starts) else doc.page_count - 1
        song_dir = OUT / "songs" / key / number_folder(item["number"])
        song_dir.mkdir(parents=True, exist_ok=True)
        images = []
        page_text = []
        lyric_verses = []
        for page_index in range(item["start"], end + 1):
            page = doc[page_index]
            source_image = legacy_image(key, page_index + 1)
            destination = song_dir / f"{page_index - item['start'] + 1:02d}.jpg"
            if source_image.exists():
                shutil.move(str(source_image), str(destination))
            else:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
                pix.save(destination, jpg_quality=82)
            images.append(destination.relative_to(ROOT).as_posix())
            page_text.append(clean(page.get_text("text")))
            lyric_verses.extend(rebuild_lyric_verses(page))
        song_id = f"{key}-{item['number']}"
        record = {
            "id": song_id,
            "collection": key,
            "number": item["number"],
            "title": item["title"],
            "images": images,
            "text": " ".join(page_text),
            "lyricText": format_lyric_text(lyric_verses),
            "lyricVerses": [format_lyric_verse(verse) for verse in lyric_verses],
        }
        write_json(song_dir / "song.json", record)
        public_songs.append(
            {field: record[field] for field in ("id", "collection", "number", "title")}
            | {"image": images[0], "data": (song_dir / "song.json").relative_to(ROOT).as_posix()}
        )
        search_songs.append(record)
    doc.close()

    shard_paths = []
    for shard_number, start in enumerate(range(0, len(search_songs), SEARCH_SHARD_SIZE), 1):
        path = OUT / "search" / key / f"part-{shard_number:02d}.json"
        write_json(path, search_songs[start : start + SEARCH_SHARD_SIZE])
        shard_paths.append(path.relative_to(ROOT).as_posix())
    write_json(
        OUT / "indexes" / f"{key}.json",
        {"collection": key, "label": label, "songs": public_songs, "searchFiles": shard_paths},
    )
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
