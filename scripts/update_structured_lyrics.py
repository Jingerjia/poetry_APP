from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "database" / "songs"
BOOKS_WITH_ONLINE = {"hymns", "supplement", "new-songs", "new-poems"}
BOOKS_WITH_LOCAL_LYRICS = {"hymns", "supplement", "blue-poems"}
USER_AGENT = "Mozilla/5.0 hymn-library-offline-builder"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6",
}


VERSE_RE = re.compile(
    r'<div class="fullscreen-verse"\s+data-type="(?P<type>[^"]+)">\s*'
    r'<div class="fullscreen-verse-num">(?P<num>.*?)</div>\s*'
    r'<div class="fullscreen-verse-text(?: chorus)?">(?P<text>.*?)</div>',
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")
P_RE = re.compile(r"<p(?:\s[^>]*)?>(?P<text>.*?)</p>", re.S | re.I)
HAN_RE = re.compile(r"[\u3400-\u9fff]")
FLOWINGSTREAM_END_RE = re.compile(
    r'(?:class="[^"]*the_champ_sharing_container|分享出去|id="comments"|class="[^"]*comments)',
    re.I,
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_if_changed(path: Path, data) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == text:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def text_from_html(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = TAG_RE.sub("", fragment)
    value = html.unescape(fragment).replace("\r", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def fetch_html(url: str, retries: int = 3) -> str:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"{url} {last_error}")


def parse_hymnal_html(page: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for match in VERSE_RE.finditer(page):
        kind = "chorus" if match.group("type") == "chorus" else "verse"
        number = text_from_html(match.group("num"))
        text = text_from_html(match.group("text"))
        if not text:
            continue
        sections.append({"type": kind, "number": number, "text": text})
    return clear_repeated_chorus_numbers(sections)


def flowingstream_body(page: str) -> str:
    start_candidates = [
        page.lower().find('class="pdfjs-iframe"'),
        page.lower().find("embedded pdf"),
    ]
    starts = [index for index in start_candidates if index >= 0]
    body = page[min(starts) :] if starts else page
    end = FLOWINGSTREAM_END_RE.search(body)
    return body[: end.start()] if end else body


def parse_section_label(label: str) -> tuple[str, str] | None:
    value = label.strip().strip(".、:：")
    value = value.strip("()（）")
    chorus_match = re.fullmatch(r"(副歌?|合)(?:\s*(\d{1,2})\s*[~～\-－]\s*(\d{1,2})|\s*(\d{1,2}))?", value)
    if chorus_match:
        if chorus_match.group(2) and chorus_match.group(3):
            return "chorus", f"{chorus_match.group(2)}~{chorus_match.group(3)}"
        if chorus_match.group(4):
            return "chorus", chorus_match.group(4)
        return "chorus", ""
    if re.fullmatch(r"\d{1,2}", value):
        return "verse", value
    return None


def parse_embedded_section_marker(line: str) -> tuple[str, str] | None:
    value = line.strip()
    if not value:
        return None
    chorus_match = re.fullmatch(r"[（(]?\s*副(?:歌)?\s*[)）]?(?:\s*(\d{1,2})\s*[~～\-－]\s*(\d{1,2})|\s*(\d{1,2}))?", value)
    if chorus_match:
        if chorus_match.group(1) and chorus_match.group(2):
            return "chorus", f"{chorus_match.group(1)}~{chorus_match.group(2)}"
        if chorus_match.group(3):
            return "chorus", chorus_match.group(3)
        return "chorus", ""
    return parse_section_label(value)


def split_embedded_sections(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for section in sections:
        kind = str(section.get("type") or "verse")
        number = str(section.get("number") or "")
        lines = [line.rstrip() for line in str(section.get("text") or "").splitlines()]
        current_kind = kind
        current_number = number
        current_lines: list[str] = []

        def flush() -> None:
            text = "\n".join(line for line in current_lines if line.strip()).strip()
            if text:
                result.append({"type": current_kind, "number": current_number, "text": text})

        for line in lines:
            marker = parse_embedded_section_marker(line)
            if marker:
                flush()
                current_kind, current_number = marker
                current_lines = []
                continue
            current_lines.append(line)
        flush()
    return result


def normalize_section_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def clear_repeated_chorus_numbers(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    choruses = [section for section in sections if section.get("type") == "chorus"]
    unique_texts = {normalize_section_text(section.get("text", "")) for section in choruses}
    unique_texts.discard("")
    if len(unique_texts) <= 1:
        for section in choruses:
            section["number"] = ""
    return sections


def parse_flowingstream_html(page: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    pending_label: tuple[str, str] | None = None
    for match in P_RE.finditer(flowingstream_body(page)):
        text = text_from_html(match.group("text"))
        if not text or not HAN_RE.search(text):
            label = parse_section_label(text) if text else None
            if label:
                pending_label = label
            continue
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            continue

        label = parse_section_label(lines[0])
        content_lines = lines[1:]
        if label is None:
            first = lines[0]
            chorus_match = re.match(r"^[（(]?\s*副(?:歌)?\s*[)）]?\s*(.*)$", first)
            verse_match = re.match(r"^(\d{1,2})[.、:：\s]+(.+)$", first)
            if chorus_match:
                label = ("chorus", "")
                if chorus_match.group(1).strip():
                    content_lines = [chorus_match.group(1).strip(), *lines[1:]]
            elif verse_match:
                label = ("verse", verse_match.group(1))
                content_lines = [verse_match.group(2).strip(), *lines[1:]]
            elif pending_label:
                label = pending_label
                content_lines = lines
                pending_label = None
            else:
                if sections:
                    sections[-1]["text"] = f"{sections[-1]['text']}\n{text}".strip()
                continue
        else:
            pending_label = None

        text = "\n".join(content_lines).strip()
        if text:
            kind, number = label
            sections.append({"type": kind, "number": number, "text": text})
    return clear_repeated_chorus_numbers(split_embedded_sections(sections))


def parse_online_html(url: str, page: str) -> list[dict[str, str]]:
    if "flowingstream.org" in url:
        return parse_flowingstream_html(page)
    return parse_hymnal_html(page)


def sections_from_plain_text(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    verse_number = 1
    raw_text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", raw_text) if block.strip()]
    if len(blocks) == 1:
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        if len(lines) > 1 and not parse_section_label(lines[0]):
            blocks = lines
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0]
        label = parse_section_label(first)
        content_lines = lines[1:]
        if label is None:
            chorus_match = re.match(r"^[（(]?\s*副(?:歌)?\s*[)）]?\s*(.*)$", first)
            verse_match = re.match(r"^(\d{1,2})[.、:：\s]+(.+)$", first)
            if chorus_match:
                label = ("chorus", "")
                content_lines = [chorus_match.group(1).strip(), *lines[1:]]
            elif verse_match:
                label = ("verse", verse_match.group(1))
                content_lines = [verse_match.group(2).strip(), *lines[1:]]
            else:
                label = ("verse", str(verse_number))
                verse_number += 1
                content_lines = lines
        text_value = "\n".join(line for line in content_lines if line).strip()
        if not text_value:
            continue
        kind, number = label
        sections.append({"type": kind, "number": number, "text": text_value})
    return clear_repeated_chorus_numbers(sections)


def update_online_song(path: Path) -> tuple[str, bool, str]:
    song = read_json(path)
    if song.get("structuredLyrics"):
        return str(path), False, "exists"
    url = song.get("onlineLyricsSource")
    if not url:
        sections = sections_from_plain_text(str(song.get("lyricText") or ""))
        if not sections:
            return str(path), False, "no source"
        song["structuredLyrics"] = sections
        changed = write_json_if_changed(path, song)
        return str(path), changed, f"{len(sections)} local sections"
    try:
        sections = parse_online_html(url, fetch_html(url))
    except Exception as error:
        if "flowingstream.org" not in url:
            raise
        sections = sections_from_plain_text(str(song.get("lyricText") or ""))
        if not sections:
            raise error
        song["structuredLyrics"] = sections
        changed = write_json_if_changed(path, song)
        return str(path), changed, f"{len(sections)} local sections after fetch error"
    if not sections:
        sections = sections_from_plain_text(str(song.get("lyricText") or "")) if "flowingstream.org" in url else []
        if not sections:
            return str(path), False, "no lyrics"
        song["structuredLyrics"] = sections
        changed = write_json_if_changed(path, song)
        return str(path), changed, f"{len(sections)} local sections"
    song["structuredLyrics"] = clear_repeated_chorus_numbers(sections)
    changed = write_json_if_changed(path, song)
    return str(path), changed, f"{len(sections)} sections"


def update_local_lyrics_song(path: Path) -> tuple[str, bool, str]:
    song = read_json(path)
    if song.get("structuredLyrics"):
        return str(path), False, "exists"
    folder = path.parent
    lyrics_path = folder / "lyrics.json"
    if not lyrics_path.exists():
        return str(path), False, "no lyrics.json"
    raw = read_json(lyrics_path)
    if not isinstance(raw, list):
        return str(path), False, "lyrics not list"
    sections = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("lyrics") or "").strip()
        if not text:
            continue
        number = str(item.get("verse_no") or "").strip()
        kind = "chorus" if str(item.get("type") or "").lower() == "chorus" or number in {"副", "副歌"} else "verse"
        sections.append({"type": kind, "number": "" if kind == "chorus" else number, "text": text})
    if not sections:
        return str(path), False, "no sections"
    song["structuredLyrics"] = clear_repeated_chorus_numbers(sections)
    changed = write_json_if_changed(path, song)
    return str(path), changed, f"{len(sections)} sections"


def main() -> int:
    song_paths = sorted(SONGS.glob("*/*/song.json"))
    online_paths = [p for p in song_paths if p.parts[-3] in BOOKS_WITH_ONLINE]
    local_paths = [p for p in song_paths if p.parts[-3] in BOOKS_WITH_LOCAL_LYRICS]
    changed = 0
    failed: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(update_online_song, path): path for path in online_paths}
        for index, future in enumerate(as_completed(futures), 1):
            path = futures[future]
            try:
                name, did_change, message = future.result()
                changed += int(did_change)
                print(f"[online {index}/{len(futures)}] {'update' if did_change else 'ok'} {path.parent.name} {message}")
            except Exception as error:
                failed.append((str(path), str(error)))
                print(f"[online {index}/{len(futures)}] fail {path.parent.name} {error}")

    for index, path in enumerate(local_paths, 1):
        try:
            name, did_change, message = update_local_lyrics_song(path)
            changed += int(did_change)
            print(f"[local {index}/{len(local_paths)}] {'update' if did_change else 'ok'} {path.parent.name} {message}")
        except Exception as error:
            failed.append((str(path), str(error)))
            print(f"[local {index}/{len(local_paths)}] fail {path.parent.name} {error}")

    print(f"Changed files: {changed}")
    if failed:
        print("Failed:")
        for path, error in failed:
            print(f"- {path}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
