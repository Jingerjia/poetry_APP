"""Overlay offline song JSON with web lyrics when a matching text page exists.

The PDF extractor remains the fallback. This script only replaces lyricText and
lyricVerses after a source page yields usable Chinese verse text.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from build_database import format_lyric_verse, write_json


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "database"
USER_AGENT = "Mozilla/5.0"
MIN_HAN_CHARS = 12

URLS = {
    "hymns": "https://www.hymnal.net/zh/hymn/ch/{number}",
    "supplement": "https://www.hymnal.net/zh/hymn/ts/{number}",
    "new-songs": "https://flowingstream.org/hymn/c{number:03d}/",
    "new-poems": "https://flowingstream.org/hymn/d{number:03d}/",
}

BLOCK_RE = re.compile(r"<(br|/p|/div|/blockquote|/li|/h[1-6])\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HYMNL_STANZAS_RE = re.compile(r'<article[^>]*class="[^"]*\bjs-stanzas\b[^"]*"[^>]*>(.*?)</article>', re.I | re.S)
HYMNL_TEXT_RE = re.compile(r'<div[^>]*class="[^"]*\btext-container\b[^"]*"[^>]*>(.*?)</div>', re.I | re.S)
FLOWING_VERSE_RE = re.compile(
    r"<blockquote>\s*<p>\s*<strong>\s*(?:\d+|副)\s*</strong>\s*</p>\s*</blockquote>\s*"
    r"<p[^>]*>(.*?)</p>",
    re.I | re.S,
)
FLOWING_CONTENT_RE = re.compile(r'<div[^>]*class="[^"]*\bpakb-article-content\b[^"]*"[^>]*>(.*?)</article>', re.I | re.S)
PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)


def request_url(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_html(url: str) -> str:
    with urllib.request.urlopen(request_url(url), timeout=35) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def html_to_lines(fragment: str) -> list[str]:
    fragment = BLOCK_RE.sub("\n", fragment)
    fragment = TAG_RE.sub("", fragment)
    fragment = html.unescape(fragment)
    lines = []
    for line in fragment.splitlines():
        line = re.sub(r"\s+", "", line)
        line = re.sub(r"^[\d一二三四五六七八九十]+[.)）、、]?", "", line)
        line = re.sub(r"^副[.)）、、]?", "", line)
        if re.search(r"[\u4e00-\u9fff]", line):
            lines.append(line)
    return lines


def compact_verse(lines: list[str]) -> str:
    return format_lyric_verse("".join(lines))


def parse_hymnal(page: str) -> list[str]:
    article_match = HYMNL_STANZAS_RE.search(page)
    if not article_match:
        return []
    verses = []
    for fragment in HYMNL_TEXT_RE.findall(article_match.group(1)):
        verse = compact_verse(html_to_lines(fragment))
        if han_count(verse) >= MIN_HAN_CHARS:
            verses.append(verse)
    return verses


def parse_flowingstream(page: str) -> list[str]:
    verses = []
    for fragment in FLOWING_VERSE_RE.findall(page):
        verse = compact_verse(html_to_lines(fragment))
        if han_count(verse) >= MIN_HAN_CHARS:
            verses.append(verse)
    if verses:
        return verses

    content_match = FLOWING_CONTENT_RE.search(page)
    if not content_match:
        return []
    content = re.split(r"<div[^>]+the_champ_sharing_container\b", content_match.group(1), maxsplit=1, flags=re.I)[0]
    for fragment in PARAGRAPH_RE.findall(content):
        lines = html_to_lines(fragment)
        if not lines:
            continue
        verse = compact_verse(lines)
        if han_count(verse) >= MIN_HAN_CHARS:
            verses.append(verse)
    return verses


def han_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def number_folder(number) -> str:
    if isinstance(number, int):
        return f"{number:04d}"
    return f"A{int(str(number).replace(chr(0x9644), '')):03d}"


def source_number(book: str, number) -> int:
    if book == "hymns" and isinstance(number, str) and number.startswith(chr(0x9644)):
        return 1000 + int(number.replace(chr(0x9644), ""))
    return int(number)


def song_path(book: str, number) -> Path:
    return DATABASE / "songs" / book / number_folder(number) / "song.json"


def songs_for(book: str) -> list[dict]:
    path = DATABASE / "indexes" / f"{book}.json"
    return json.loads(path.read_text(encoding="utf-8"))["songs"]


def parse_page(book: str, page: str) -> list[str]:
    if book in {"hymns", "supplement"}:
        return parse_hymnal(page)
    return parse_flowingstream(page)


def source_urls(book: str, number) -> list[str]:
    source = source_number(book, number)
    urls = [URLS[book].format(number=source)]
    if book == "new-poems":
        urls.append(f"https://flowingstream.org/hymn/d{source}/")
    return list(dict.fromkeys(urls))


def has_online_lyrics(book: str, number) -> bool:
    path = song_path(book, number)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return bool(data.get("onlineLyricsSource"))


def update_one(book: str, song: dict, dry_run: bool = False, retries: int = 2, retry_delay: float = 3.0) -> str:
    number = song["number"]
    urls = source_urls(book, number)
    for attempt in range(retries + 1):
        try:
            last_no_text = None
            for url in urls:
                try:
                    page = fetch_html(url)
                except urllib.error.HTTPError as error:
                    if error.code == 404 and url != urls[-1]:
                        continue
                    raise
                verses = parse_page(book, page)
                lyric_text = "\n".join(verses)
                if han_count(lyric_text) >= MIN_HAN_CHARS:
                    break
                last_no_text = f"no-text {book} {number} {url}"
            else:
                return last_no_text or f"no-text {book} {number} {urls[0]}"
            path = song_path(book, number)
            data = json.loads(path.read_text(encoding="utf-8"))
            if not dry_run:
                data["lyricText"] = lyric_text
                data["lyricVerses"] = verses
                data["onlineLyricsSource"] = url
                write_json(path, data)
            return f"ok {book} {number} verses={len(verses)}"
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return f"miss {book} {number} HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            if attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return f"fail {book} {number} {error}"


def rebuild_search_files() -> None:
    for book in URLS:
        index_path = DATABASE / "indexes" / f"{book}.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        records = []
        for song in index["songs"]:
            records.append(json.loads((ROOT / song["data"]).read_text(encoding="utf-8")))
        for search_file in index["searchFiles"]:
            path = ROOT / search_file
            shard_number = int(path.stem.split("-")[-1])
            start = (shard_number - 1) * 50
            write_json(path, records[start : start + 50])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=URLS.keys())
    parser.add_argument("--number")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-missing-online", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.02)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=3.0)
    args = parser.parse_args()

    jobs = []
    books = [args.book] if args.book else list(URLS)
    for book in books:
        for song in songs_for(book):
            if args.number and str(song["number"]) != args.number:
                continue
            if args.only_missing_online and has_online_lyrics(book, song["number"]):
                continue
            jobs.append((book, song))

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(update_one, book, song, args.dry_run, args.retries, args.retry_delay) for book, song in jobs]
        for future in as_completed(futures):
            done += 1
            print(f"[{done}/{len(jobs)}] {future.result()}", flush=True)
            time.sleep(args.delay)

    if not args.dry_run:
        rebuild_search_files()
        print("Search shards rebuilt")


if __name__ == "__main__":
    main()
