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
BLUE_BOOK_KEY = "blue-poems"
BLUE_BOOK_LABEL = "\u85cd\u672c"
BLUE_BOOK_PAGE_GROUPS = {
    1: [130], 2: [131, 132], 3: [133], 4: [134, 135], 5: [136], 6: [137],
    7: [138, 139], 8: [140], 9: [141, 142], 10: [143, 144], 11: [145],
    12: [146], 13: [147], 14: [148], 15: [149, 150], 16: [151],
    17: [153, 154], 18: [155], 19: [156], 20: [157, 158], 21: [159, 160],
    22: [161], 23: [162, 163], 24: [164], 25: [165], 26: [166], 27: [167],
    28: [168, 169], 29: [170], 30: [171], 31: [172, 173], 32: [174, 175],
    33: [176], 34: [177], 35: [178], 36: [179], 37: [180], 38: [181],
    39: [182], 40: [183, 184], 41: [185, 186], 42: [187], 43: [188],
    44: [189, 190], 45: [191, 192], 46: [193, 194], 47: [195, 196],
    48: [197], 49: [198], 50: [199, 200], 51: [201], 52: [202, 203],
    53: [204], 54: [205], 55: [206, 207], 56: [208, 209], 57: [210],
    58: [211, 212], 59: [213, 214], 60: [215], 61: [216], 62: [217, 218],
    63: [219, 220], 64: [221, 222], 65: [223, 224], 66: [225, 226],
    67: [227, 228], 68: [229, 230], 69: [231, 232], 70: [233, 234],
    71: [235], 72: [236, 237], 73: [238], 74: [239, 240], 75: [241, 242],
    76: [243, 244], 77: [245, 246], 78: [247], 79: [248, 249], 80: [250],
    81: [251], 82: [252], 83: [253], 84: [254], 85: [255], 86: [256],
    87: [257], 88: [258], 89: [259], 90: [260], 91: [261], 92: [262, 263],
    93: [264], 94: [265],
}
MANUAL_SKIP_HEADINGS = {
    # The supplement PDF has a stray duplicated 133 heading before 131/132.
    ("supplement", 72, 133),
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


def first_text_line(page) -> str:
    for line in page.get_text("text").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def export_book(key: str, filename: str, label: str, first_score_page: int):
    doc = fitz.open(PDF_DIR / filename)
    starts = []
    seen_numbers = set()
    for page_index in range(first_score_page, doc.page_count):
        found = read_heading(doc[page_index].get_text("text"))
        if found:
            number, title, sort_key = found
            page_number = page_index + 1
            if (key, page_number, number) in MANUAL_SKIP_HEADINGS:
                continue
            # Reject repeated headers inside multi-page songs, but do not assume
            # the PDF itself is sorted by hymn number.
            if number not in seen_numbers:
                starts.append({"number": number, "title": title, "sortKey": sort_key, "start": page_index})
                seen_numbers.add(number)

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


def blue_pdf_path() -> Path:
    matches = [path for path in PDF_DIR.glob("*.pdf") if "\u85cd\u672c" in path.name]
    if not matches:
        raise FileNotFoundError("blue poem PDF not found")
    return matches[0]


def export_blue_book():
    doc = fitz.open(blue_pdf_path())

    public_songs = []
    search_songs = []
    for number, page_numbers in BLUE_BOOK_PAGE_GROUPS.items():
        song_dir = OUT / "songs" / BLUE_BOOK_KEY / number_folder(number)
        song_dir.mkdir(parents=True, exist_ok=True)
        images = []
        for image_index, page_number in enumerate(page_numbers, 1):
            page = doc[page_number - 1]
            destination = song_dir / f"{image_index:02d}.jpg"
            pix = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
            pix.save(destination, jpg_quality=82)
            images.append(destination.relative_to(ROOT).as_posix())
        title = f"\u85cd\u672c\u65b0\u8a69 {number:03d}"
        record = {
            "id": f"{BLUE_BOOK_KEY}-{number}",
            "collection": BLUE_BOOK_KEY,
            "number": number,
            "title": title,
            "images": images,
            "image": images[0],
            "text": "",
            "lyricText": "",
            "lyricVerses": [],
            "sourcePdfPages": page_numbers,
        }
        write_json(song_dir / "song.json", record)
        public_songs.append(
            {field: record[field] for field in ("id", "collection", "number", "title")}
            | {"image": images[0], "data": (song_dir / "song.json").relative_to(ROOT).as_posix()}
        )
        search_songs.append(record)

    shard_paths = []
    for shard_number, start in enumerate(range(0, len(search_songs), SEARCH_SHARD_SIZE), 1):
        path = OUT / "search" / BLUE_BOOK_KEY / f"part-{shard_number:02d}.json"
        write_json(path, search_songs[start : start + SEARCH_SHARD_SIZE])
        shard_paths.append(path.relative_to(ROOT).as_posix())
    write_json(
        OUT / "indexes" / f"{BLUE_BOOK_KEY}.json",
        {"collection": BLUE_BOOK_KEY, "label": BLUE_BOOK_LABEL, "songs": public_songs, "searchFiles": shard_paths},
    )
    doc.close()
    print(f"Built {BLUE_BOOK_LABEL}: {len(public_songs)} songs, {len(shard_paths)} search files")


def main():
    OUT.mkdir(exist_ok=True)
    for directory in (OUT / "indexes", OUT / "search", OUT / "songs"):
        if directory.exists():
            shutil.rmtree(directory)
    for key, (filename, label, first_score_page) in BOOKS.items():
        export_book(key, filename, label, first_score_page)
    export_blue_book()
    if LEGACY_PAGES.exists():
        shutil.rmtree(LEGACY_PAGES)
    catalog = OUT / "catalog.json"
    if catalog.exists():
        catalog.unlink()
    write_json(OUT / "manifest.json", {"version": 2, "books": list(BOOKS) + [BLUE_BOOK_KEY]})
    print("Offline database complete:", OUT)


if __name__ == "__main__":
    main()
