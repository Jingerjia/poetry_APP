from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "database" / "songs"
AUDIT = ROOT / "chorus_number_audit.md"

VARIANTS = {
    "阿": "啊",
    "呵": "啊",
    "哦": "喔",
    "裏": "裡",
    "爲": "為",
    "祢": "你",
    "袮": "你",
    "纔": "才",
}


def normalize_char(char: str) -> str:
    return VARIANTS.get(char, char)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", "".join(normalize_char(ch) for ch in str(text or "")))


def han_chars(text: str) -> list[str]:
    return [normalize_char(ch) for ch in str(text or "") if "\u3400" <= ch <= "\u9fff"]


def lyric_pattern(text: str) -> re.Pattern[str] | None:
    chars = han_chars(text)[:5]
    if len(chars) < 3:
        return None
    char_classes = []
    for char in chars:
        if char == "啊":
            char_classes.append("[啊阿呵]")
        elif char == "喔":
            char_classes.append("[喔哦]")
        elif char == "裡":
            char_classes.append("[裡裏]")
        elif char == "你":
            char_classes.append("[你祢袮]")
        else:
            char_classes.append(re.escape(char))
    return re.compile(r".{0,8}".join(char_classes), re.S)


def source_chorus_number(song: dict, chorus_text: str) -> str:
    source = str(song.get("text") or "")
    pattern = lyric_pattern(chorus_text)
    if not source or not pattern:
        return ""
    match = pattern.search(source)
    if not match:
        return ""
    before = source[max(0, match.start() - 140) : match.start()]
    last_chorus = max(before.rfind("副"), before.rfind("合"))
    if last_chorus >= 0:
        before = before[last_chorus:]
    labels = list(
        re.finditer(
            r"(?<![\dA-Za-z`])(\d{1,2})\s*[-~～－]\s*(\d{1,2})(?![\dA-Za-z])|"
            r"(?<![\dA-Za-z`])(\d{1,2})(?![\dA-Za-z])",
            before,
        )
    )
    if not labels:
        return ""
    label = labels[-1]
    if label.group(1) and label.group(2):
        return f"{label.group(1)}~{label.group(2)}"
    return label.group(3) or ""


def verse_number(value: object) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def infer_chorus_number(sections: list[dict], index: int) -> str:
    previous = None
    next_number = None
    for section in reversed(sections[:index]):
        if section.get("type") != "chorus":
            previous = verse_number(section.get("number"))
            if previous is not None:
                break
    for section in sections[index + 1 :]:
        if section.get("type") != "chorus":
            next_number = verse_number(section.get("number"))
            if next_number is not None:
                break
    if previous is not None:
        return str(previous)
    if next_number is not None:
        return str(next_number)
    return ""


def fix_song(song: dict) -> bool:
    sections = song.get("structuredLyrics")
    if not isinstance(sections, list):
        return False
    choruses = [section for section in sections if section.get("type") == "chorus"]
    if not choruses:
        return False
    unique_choruses = {normalize_text(section.get("text", "")) for section in choruses}
    unique_choruses.discard("")
    changed = False

    if len(unique_choruses) <= 1:
        for section in choruses:
            if section.get("number"):
                section["number"] = ""
                changed = True
        return changed

    for index, section in enumerate(sections):
        if section.get("type") != "chorus":
            continue
        number = source_chorus_number(song, str(section.get("text") or "")) or infer_chorus_number(sections, index)
        if section.get("number") != number:
            section["number"] = number
            changed = True
    return changed


def main() -> int:
    changed_paths: list[Path] = []
    numbered: list[tuple[str, str, int, str, str]] = []
    repeated_songs = 0
    bad_ranges: list[tuple[str, str, str]] = []
    empty_different_choruses: list[tuple[str, str]] = []
    same_number_different_choruses: list[tuple[str, str, str]] = []

    for path in sorted(SONGS.glob("*/*/song.json")):
        song = json.loads(path.read_text(encoding="utf-8"))
        if fix_song(song):
            path.write_text(json.dumps(song, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            changed_paths.append(path)

        choruses = [section for section in song.get("structuredLyrics", []) if section.get("type") == "chorus"]
        unique_choruses = {normalize_text(section.get("text", "")) for section in choruses}
        unique_choruses.discard("")
        if choruses and len(unique_choruses) <= 1:
            repeated_songs += 1
        if len(unique_choruses) > 1 and any(not str(section.get("number") or "").strip() for section in choruses):
            empty_different_choruses.append((str(path), str(song.get("title") or "")))
        grouped_by_number: dict[str, set[str]] = {}
        for section in choruses:
            number = str(section.get("number") or "")
            if number:
                grouped_by_number.setdefault(number, set()).add(normalize_text(section.get("text", "")))
        for number, texts in grouped_by_number.items():
            if len(texts) > 1:
                same_number_different_choruses.append((str(path), str(song.get("title") or ""), number))
        for index, section in enumerate(song.get("structuredLyrics", []), 1):
            if section.get("type") != "chorus":
                continue
            number = str(section.get("number") or "")
            if number:
                preview = str(section.get("text") or "").split("\n")[0][:40]
                numbered.append((str(path), str(song.get("title") or ""), index, number, preview))
            match = re.fullmatch(r"(\d+)~(\d+)", number)
            if match and int(match.group(1)) > int(match.group(2)):
                bad_ranges.append((str(path), str(song.get("title") or ""), number))

    lines = [
        "# Chorus Number Audit",
        "",
        "規則：同一首歌內副歌文字都一樣時，chorus.number 保持空字串；只有同一首內有不同副歌文字時，才保留 number 來標示適用節數。",
        "",
        f"- changed files in latest fix: {len(changed_paths)}",
        f"- songs with repeated identical chorus cleared: {repeated_songs}",
        f"- chorus sections with different text and number kept: {len(numbered)}",
        f"- invalid descending ranges: {len(bad_ranges)}",
        f"- different choruses without verse number, confirm manually: {len(empty_different_choruses)}",
        f"- same number used by different chorus text, confirm manually: {len(same_number_different_choruses)}",
        "",
    ]
    if bad_ranges:
        lines.append("## Invalid Ranges")
        for path, title, number in bad_ranges:
            lines.append(f"- `{path}` {title}: `{number}`")
        lines.append("")
    if empty_different_choruses or same_number_different_choruses:
        lines.append("## Needs Manual Confirmation")
        for path, title in empty_different_choruses:
            lines.append(f"- `{path}` {title}: different chorus text has no verse number, possibly duet/part singing.")
        for path, title, number in same_number_different_choruses:
            lines.append(f"- `{path}` {title}: different chorus text shares `{number}`.")
        lines.append("")
    lines.append("## Numbered Choruses")
    for path, title, index, number, preview in numbered:
        lines.append(f"- `{path}` {title} section {index}: `{number}` - {preview}")
    AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"changed_files {len(changed_paths)}")
    print(f"numbered_choruses {len(numbered)}")
    print(f"bad_ranges {len(bad_ranges)}")
    for path in changed_paths[:120]:
        print(path)
    return 1 if bad_ranges else 0


if __name__ == "__main__":
    raise SystemExit(main())
