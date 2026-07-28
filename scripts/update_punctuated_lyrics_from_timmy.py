from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "database" / "songs"
AUDIT = ROOT / "timmy_lyrics_update_audit.md"
TIMMY_URL = "https://timmyhymn.github.io/Thymn/hymns.js"
BOOK_MAP = {
    "new-songs": 3,
    "new-poems": 4,
}
PUNCTUATION = set("，。！？、；：,.!?;:；")
USER_AGENT = "Mozilla/5.0 poetry-app-punctuation-updater"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def has_han(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in text)


def has_punctuation(text: str) -> bool:
    return any(char in PUNCTUATION for char in text)


def needs_punctuation(song: dict) -> bool:
    sections = song.get("structuredLyrics") or []
    text = "".join(str(section.get("text") or "") for section in sections)
    return bool(text and has_han(text) and not has_punctuation(text))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def join_orphan_punctuation(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if line in PUNCTUATION and result:
            result[-1] = f"{result[-1]}{line}"
        else:
            result.append(line)
    return result


def range_label(numbers: list[int]) -> str:
    if not numbers:
        return ""
    unique = sorted(set(numbers))
    if len(unique) == 1:
        return str(unique[0])
    return f"{unique[0]}~{unique[-1]}"


def parse_timmy_lyrics(raw: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    current_lines: list[str] = []
    seen_first_marker = False

    def flush() -> None:
        nonlocal current, current_lines
        if current and current_lines:
            text = "\n".join(join_orphan_punctuation(current_lines)).strip()
            if text:
                sections.append({**current, "text": text})
        current = None
        current_lines = []

    for line in lines:
        verse_match = re.fullmatch(r"\d{1,2}", line)
        chorus_match = re.fullmatch(r"[（(]\s*副(?:歌)?\s*[)）]", line)
        if verse_match:
            flush()
            seen_first_marker = True
            current = {"type": "verse", "number": line}
            continue
        if chorus_match:
            flush()
            seen_first_marker = True
            current = {"type": "chorus", "number": ""}
            continue
        if not seen_first_marker:
            continue
        if current:
            current_lines.append(line)
    flush()
    if not sections:
        body_lines = lines[:]
        if body_lines:
            body_lines = body_lines[1:]
        if body_lines and (re.search(r"\d\s*/\s*\d", body_lines[0]) or "調" in body_lines[0]):
            body_lines = body_lines[1:]
        text = "\n".join(join_orphan_punctuation(body_lines)).strip()
        if text:
            sections = [{"type": "verse", "number": "1", "text": text}]
    return consolidate_choruses(sections)


def consolidate_choruses(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    choruses = [section for section in sections if section.get("type") == "chorus"]
    unique_choruses = {normalize_text(section.get("text", "")) for section in choruses}
    unique_choruses.discard("")
    if len(unique_choruses) <= 1:
        for section in choruses:
            section["number"] = ""
        return sections

    grouped: dict[str, dict] = {}
    result: list[dict[str, str]] = []
    last_verse_number: int | None = None
    for section in sections:
        if section.get("type") != "chorus":
            result.append(section)
            match = re.search(r"\d+", str(section.get("number") or ""))
            if match:
                last_verse_number = int(match.group(0))
            continue
        key = normalize_text(section.get("text", ""))
        if key not in grouped:
            grouped[key] = {"section": {**section}, "numbers": []}
            result.append(grouped[key]["section"])
        if last_verse_number is not None:
            grouped[key]["numbers"].append(last_verse_number)
    for item in grouped.values():
        item["section"]["number"] = range_label(item["numbers"])
    return result


def fetch_timmy_data() -> dict[tuple[int, int], dict]:
    request = urllib.request.Request(TIMMY_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        source = response.read().decode("utf-8", "replace")
    match = re.search(r"const\s+hymns\s*=\s*(\[.*?\])\s*;", source, re.S)
    if not match:
        raise RuntimeError("Could not find hymns array in hymns.js")
    hymns = json.loads(match.group(1))
    return {(int(item["book"]), int(item["code"])): item for item in hymns}


def main() -> int:
    targets = []
    for book in BOOK_MAP:
        for path in sorted((SONGS / book).glob("*/song.json")):
            song = read_json(path)
            if needs_punctuation(song):
                targets.append((book, path, song))

    if not targets:
        AUDIT.write_text("# Timmy Lyrics Update Audit\n\nNo songs needed punctuation updates.\n", encoding="utf-8", newline="\n")
        print("No targets")
        return 0

    # One request for the complete data source, then local processing only.
    data = fetch_timmy_data()
    time.sleep(1.5)

    changed: list[str] = []
    missing: list[str] = []
    no_sections: list[str] = []
    skipped_no_punctuation: list[str] = []

    for book, path, song in targets:
        item = data.get((BOOK_MAP[book], int(song["number"])))
        if not item:
            missing.append(str(path))
            continue
        sections = parse_timmy_lyrics(str(item.get("lyrics") or ""))
        text = "".join(section.get("text", "") for section in sections)
        if not sections:
            no_sections.append(str(path))
            continue
        if not has_punctuation(text):
            skipped_no_punctuation.append(str(path))
            continue
        song["structuredLyrics"] = sections
        write_json(path, song)
        changed.append(str(path))

    lines = [
        "# Timmy Lyrics Update Audit",
        "",
        "來源：`https://timmyhymn.github.io/Thymn/hymns.js`。本腳本只發出一次請求，之後在本機處理，避免逐首請求造成網站負擔。",
        "",
        f"- targets without punctuation before update: {len(targets)}",
        f"- changed files: {len(changed)}",
        f"- missing in Timmy data: {len(missing)}",
        f"- parsed no sections: {len(no_sections)}",
        f"- source still had no punctuation: {len(skipped_no_punctuation)}",
        "",
    ]
    if changed:
        lines.append("## Updated")
        lines.extend(f"- `{path}`" for path in changed)
        lines.append("")
    if missing or no_sections or skipped_no_punctuation:
        lines.append("## Needs Review")
        for path in missing:
            lines.append(f"- `{path}` missing in Timmy data")
        for path in no_sections:
            lines.append(f"- `{path}` parsed no sections")
        for path in skipped_no_punctuation:
            lines.append(f"- `{path}` source still had no punctuation")
    AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"targets {len(targets)}")
    print(f"changed {len(changed)}")
    print(f"missing {len(missing)}")
    print(f"no_sections {len(no_sections)}")
    print(f"skipped_no_punctuation {len(skipped_no_punctuation)}")
    for path in changed[:120]:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
