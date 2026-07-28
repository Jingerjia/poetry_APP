from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "database" / "songs"
AUDIT = ROOT / "verse_number_audit.md"


def number_value(value: object) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def infer_empty_verse_numbers(sections: list[dict]) -> bool:
    changed = False
    verse_counter = 0
    for section in sections:
        if section.get("type") == "chorus":
            continue
        current = str(section.get("number") or "").strip()
        if current:
            parsed = number_value(current)
            if parsed is not None:
                verse_counter = parsed
            continue
        verse_counter += 1
        section["number"] = str(verse_counter)
        changed = True
    return changed


def numeric_verse_sequence(sections: list[dict]) -> list[int]:
    numbers: list[int] = []
    for section in sections:
        if section.get("type") == "chorus":
            continue
        number = number_value(section.get("number"))
        if number is not None:
            numbers.append(number)
    return numbers


def is_contiguous_from_first(numbers: list[int]) -> bool:
    if not numbers:
        return True
    return numbers == list(range(numbers[0], numbers[0] + len(numbers)))


def main() -> int:
    changed_paths: list[Path] = []
    empty_after: list[tuple[str, str, str]] = []
    non_contiguous: list[tuple[str, str, list[int]]] = []

    for path in sorted(SONGS.glob("*/*/song.json")):
        song = json.loads(path.read_text(encoding="utf-8"))
        sections = song.get("structuredLyrics")
        if not isinstance(sections, list):
            continue
        if infer_empty_verse_numbers(sections):
            path.write_text(json.dumps(song, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            changed_paths.append(path)

        for section in sections:
            if section.get("type") != "chorus" and not str(section.get("number") or "").strip():
                preview = str(section.get("text") or "").split("\n")[0][:40]
                empty_after.append((str(path), str(song.get("title") or ""), preview))
        numbers = numeric_verse_sequence(sections)
        if numbers and not is_contiguous_from_first(numbers):
            non_contiguous.append((str(path), str(song.get("title") or ""), numbers))

    lines = [
        "# Verse Number Audit",
        "",
        "修正規則：只補 `structuredLyrics` 裡 type 不是 chorus 且 number 空白的段落；依照同一首歌中已出現的 verse 順序遞增，chorus 不計入節數。",
        "",
        f"- changed files: {len(changed_paths)}",
        f"- remaining empty verse numbers: {len(empty_after)}",
        f"- non-contiguous numbered verse sequences for manual review: {len(non_contiguous)}",
        "",
    ]
    if changed_paths:
        lines.append("## Fixed Empty Verse Numbers")
        for path in changed_paths:
            lines.append(f"- `{path}`")
        lines.append("")
    if empty_after:
        lines.append("## Remaining Empty Verse Numbers")
        for path, title, preview in empty_after:
            lines.append(f"- `{path}` {title}: {preview}")
        lines.append("")
    if non_contiguous:
        lines.append("## Non-Contiguous Verse Numbers")
        for path, title, numbers in non_contiguous:
            lines.append(f"- `{path}` {title}: {numbers}")
    AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"changed_files {len(changed_paths)}")
    print(f"remaining_empty {len(empty_after)}")
    print(f"non_contiguous {len(non_contiguous)}")
    for path in changed_paths[:120]:
        print(path)
    return 1 if empty_after else 0


if __name__ == "__main__":
    raise SystemExit(main())
