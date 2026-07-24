from pathlib import Path
import json
import re


ROOT = Path("database/songs/blue-poems")
INDEX = Path("database/indexes/blue-poems.json")
SEARCH = Path("database/search/blue-poems")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def title_from_lyrics(items):
    verse = ""
    for item in items:
        if "verse_no" in item:
            verse = str(item.get("lyrics") or "")
            break
    parts = [part.strip() for part in re.split(r"[，,。！？!；;：:\s]+", verse) if part.strip()]
    if not parts:
        return ""
    title = parts[0]
    index = 1
    while len(title) < 4 and index < len(parts):
        title += parts[index]
        index += 1
    return title[:18]


def main():
    titles = {}
    for folder in sorted(ROOT.glob("[0-9][0-9][0-9][0-9]")):
        lyrics_path = folder / "lyrics.json"
        song_path = folder / "song.json"
        if not lyrics_path.exists() or not song_path.exists():
            continue
        title = title_from_lyrics(read_json(lyrics_path))
        if not title:
            continue
        data = read_json(song_path)
        data["title"] = title
        write_json(song_path, data)
        titles[data["id"]] = title
        print(data["number"], title)

    if INDEX.exists():
        index = read_json(INDEX)
        for song in index.get("songs", []):
            if song.get("id") in titles:
                song["title"] = titles[song["id"]]
        write_json(INDEX, index)

    if SEARCH.exists():
        for path in sorted(SEARCH.glob("*.json")):
            rows = read_json(path)
            changed = False
            for song in rows:
                if song.get("id") in titles:
                    song["title"] = titles[song["id"]]
                    changed = True
            if changed:
                write_json(path, rows)


if __name__ == "__main__":
    main()
