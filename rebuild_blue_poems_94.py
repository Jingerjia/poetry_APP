from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import fitz

ROOT = Path(__file__).parent
PDF = next(path for path in (ROOT / "pdf").glob("*.pdf") if "藍本" in path.name)
BLUE_DIR = ROOT / "database" / "songs" / "blue-poems"

PAGE_GROUPS = {
    1: [130],
    2: [131, 132],
    3: [133],
    4: [134, 135],
    5: [136],
    6: [137],
    7: [138, 139],
    8: [140],
    9: [141, 142],
    10: [143, 144],
    11: [145],
    12: [146],
    13: [147],
    14: [148],
    15: [149, 150],
    16: [151],
    17: [153, 154],
    18: [155],
    19: [156],
    20: [157, 158],
    21: [159, 160],
    22: [161],
    23: [162, 163],
    24: [164],
    25: [165],
    26: [166],
    27: [167],
    28: [168, 169],
    29: [170],
    30: [171],
    31: [172, 173],
    32: [174, 175],
    33: [176],
    34: [177],
    35: [178],
    36: [179],
    37: [180],
    38: [181],
    39: [182],
    40: [183, 184],
    41: [185, 186],
    42: [187],
    43: [188],
    44: [189, 190],
    45: [191, 192],
    46: [193, 194],
    47: [195, 196],
    48: [197],
    49: [198],
    50: [199, 200],
    51: [201],
    52: [202, 203],
    53: [204],
    54: [205],
    55: [206, 207],
    56: [208, 209],
    57: [210],
    58: [211, 212],
    59: [213, 214],
    60: [215],
    61: [216],
    62: [217, 218],
    63: [219, 220],
    64: [221, 222],
    65: [223, 224],
    66: [225, 226],
    67: [227, 228],
    68: [229, 230],
    69: [231, 232],
    70: [233, 234],
    71: [235],
    72: [236, 237],
    73: [238],
    74: [239, 240],
    75: [241, 242],
    76: [243, 244],
    77: [245, 246],
    78: [247],
    79: [248, 249],
    80: [250],
    81: [251],
    82: [252],
    83: [253],
    84: [254],
    85: [255],
    86: [256],
    87: [257],
    88: [258],
    89: [259],
    90: [260],
    91: [261],
    92: [262, 263],
    93: [264],
    94: [265],
}


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def git_file(path: str):
    try:
        data = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None
    return json.loads(data.decode("utf-8"))


def load_lyrics(number: int):
    current = BLUE_DIR / f"{number:04d}" / "lyrics.json"
    if current.exists():
        return json.loads(current.read_text(encoding="utf-8"))
    return git_file(f"database/songs/blue-poems/{number:04d}/lyrics.json")


def lyrics_to_text(value) -> tuple[str, list[str]]:
    if not value:
        return "", []
    rows = value.get("verses") if isinstance(value, dict) else value
    rows = rows or value.get("lyrics", []) if isinstance(value, dict) else rows
    verses = []
    for item in rows:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            label = item.get("label")
            if not label:
                label = "副歌" if item.get("chorus_no") is not None else f"第{item.get('verse_no')}節"
            body = str(item.get("lyrics") or item.get("text") or "").strip()
            text = f"{label}: {body}" if body else ""
        else:
            text = ""
        if text:
            verses.append(text)
    return "\n".join(verses), verses


def main() -> None:
    preserved_lyrics = {number: load_lyrics(number) for number in PAGE_GROUPS}
    backup = BLUE_DIR.with_name("blue-poems.pre-94-rebuild")
    if backup.exists():
        shutil.rmtree(backup)
    if BLUE_DIR.exists():
        shutil.copytree(BLUE_DIR, backup)
        shutil.rmtree(BLUE_DIR)

    doc = fitz.open(PDF)
    for number, pages in PAGE_GROUPS.items():
        song_dir = BLUE_DIR / f"{number:04d}"
        song_dir.mkdir(parents=True, exist_ok=True)
        images = []
        for index, page_number in enumerate(pages, 1):
            image = song_dir / f"{index:02d}.jpg"
            pix = doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
            pix.save(image, jpg_quality=82)
            images.append(image.relative_to(ROOT).as_posix())

        lyrics = preserved_lyrics.get(number)
        if lyrics:
            write_json(song_dir / "lyrics.json", lyrics)
        lyric_text, lyric_verses = lyrics_to_text(lyrics)
        write_json(
            song_dir / "song.json",
            {
                "id": f"blue-poems-{number}",
                "collection": "blue-poems",
                "number": number,
                "title": f"藍本新詩 {number:03d}",
                "images": images,
                "image": images[0],
                "text": lyric_text,
                "lyricText": lyric_text,
                "lyricVerses": lyric_verses,
                "sourcePdfPages": pages,
            },
        )
    doc.close()
    print("rebuilt blue-poems", len(PAGE_GROUPS))
    print("backup", backup)


if __name__ == "__main__":
    main()
