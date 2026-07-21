"""Download hymnal.net audio into the offline database.

Only the main hymnal and supplement have public audio pages. New songs and new
poems stay image/text only until matching audio sources are provided.

hymnal.net does not use one stable mp3 filename pattern for every Chinese hymn:
some songs have a Chinese vocal file, while others point to an English tune
file such as e0118_i.mp3. This downloader reads each hymn page first and then
downloads the actual mp3 URL advertised on that page.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "database"
PAGE_URLS = {
    "hymns": "https://www.hymnal.net/en/hymn/ch/{number}",
    "supplement": "https://www.hymnal.net/en/hymn/ts/{number}",
}
MP3_RE = re.compile(r"https://www\.hymnal\.net/Hymns/[^\"'<>\s]+?\.mp3")
USER_AGENT = "Mozilla/5.0"
MIN_AUDIO_BYTES = 64_000


def song_number(song: dict):
    return song["number"]


def number_key(number) -> str:
    if isinstance(number, int):
        return f"{number:04d}"
    return str(number)


def display_number(number) -> str:
    return f"{number:04d}" if isinstance(number, int) else str(number)


def source_number(book: str, number):
    if book == "hymns" and isinstance(number, str) and number.startswith("\u9644"):
        return 1000 + int(number.replace("\u9644", ""))
    return int(number)


def songs_for(book: str):
    with (DATABASE / "indexes" / f"{book}.json").open("r", encoding="utf-8") as file:
        return json.load(file)["songs"]


def request_url(url: str):
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(request_url(url), timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def page_audio_urls(book: str, number: int) -> list[str]:
    page_url = PAGE_URLS[book].format(number=number)
    page = html.unescape(fetch_text(page_url))
    urls = [url.split("?")[0] for url in MP3_RE.findall(page)]
    return list(dict.fromkeys(urls))


def audio_score(book: str, url: str) -> tuple[int, str]:
    score = 0
    if book == "hymns" and "/Chinese/mp3/" in url:
        score += 100
    if book == "supplement" and "/ChineseTS/mp3/" in url:
        score += 100
    if "_vocal.mp3" in url:
        score += 50
    if "_full.mp3" in url:
        score += 35
    if "_i.mp3" in url:
        score += 25
    return score, url


def pick_audio_url(book: str, number: int) -> str | None:
    urls = page_audio_urls(book, number)
    if not urls:
        return None
    return max(urls, key=lambda url: audio_score(book, url))


def download_one(book: str, song: dict) -> str:
    number = song_number(song)
    target = DATABASE / "audio" / book / f"{number_key(number)}.mp3"
    if target.exists() and target.stat().st_size > MIN_AUDIO_BYTES:
        return f"skip {book} {display_number(number)}"

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")

    for attempt in range(3):
        try:
            url = pick_audio_url(book, source_number(book, number))
            if not url:
                return f"no-audio {book} {display_number(number)}"
            with urllib.request.urlopen(request_url(url), timeout=60) as response:
                if response.status != 200:
                    return f"miss {book} {display_number(number)} {response.status}"
                tmp.write_bytes(response.read())
            if tmp.stat().st_size <= MIN_AUDIO_BYTES:
                tmp.unlink(missing_ok=True)
                return f"tiny {book} {display_number(number)} {Path(url).name}"
            tmp.replace(target)
            return f"ok {book} {display_number(number)} <- {Path(url).name}"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt == 2:
                tmp.unlink(missing_ok=True)
                return f"fail {book} {display_number(number)} {error}"
            time.sleep(1 + attempt)
    return f"fail {book} {number:04d}"


def main():
    jobs = [(book, song) for book in PAGE_URLS for song in songs_for(book)]
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download_one, book, song) for book, song in jobs]
        for future in as_completed(futures):
            done += 1
            print(f"[{done}/{len(jobs)}] {future.result()}", flush=True)


if __name__ == "__main__":
    main()
