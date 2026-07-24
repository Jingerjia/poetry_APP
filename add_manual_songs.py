from pathlib import Path
import json


TARGETS = [
    ("hymns", 355),
    ("supplement", 827),
]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


def lyric_parts(items):
    title = ""
    verses = []
    for item in items:
        if "title" in item:
            title = str(item.get("title") or "").strip()
        elif "lyrics" in item:
            text = str(item.get("lyrics") or "").strip()
            if text:
                verses.append(text)
    return title, verses


def song_paths(collection, number):
    folder = Path("database/songs") / collection / f"{number:04d}"
    return folder, folder / "song.json", folder / "lyrics.json"


def make_song(collection, number):
    folder, song_path, lyrics_path = song_paths(collection, number)
    lyrics = read_json(lyrics_path)
    title, verses = lyric_parts(lyrics)
    images = [str(path).replace("\\", "/") for path in sorted(folder.glob("*.jpg"))]
    song = {
        "id": f"{collection}-{number}",
        "collection": collection,
        "number": number,
        "title": title,
        "images": images,
        "text": "\n".join([title, *verses]).strip(),
        "lyricText": "\n".join(verses),
        "lyricVerses": verses,
    }
    write_json(song_path, song)
    return song


def index_summary(song):
    return {
        "id": song["id"],
        "collection": song["collection"],
        "number": song["number"],
        "title": song["title"],
        "image": song["images"][0] if song.get("images") else "",
        "data": f"database/songs/{song['collection']}/{song['number']:04d}/song.json",
    }


def sort_key(song):
    number = song.get("number")
    return (1, str(number)) if isinstance(number, str) else (0, int(number))


def update_index(collection, song):
    path = Path("database/indexes") / f"{collection}.json"
    data = read_json(path)
    songs = [item for item in data.get("songs", []) if item.get("id") != song["id"]]
    songs.append(index_summary(song))
    data["songs"] = sorted(songs, key=sort_key)
    write_json(path, data)


def update_search(collection, song):
    folder = Path("database/search") / collection
    rows = []
    for path in sorted(folder.glob("part-*.json")):
        rows.extend(read_json(path))
    rows = [item for item in rows if item.get("id") != song["id"]]
    rows.append(song)
    rows = sorted(rows, key=sort_key)
    for path in folder.glob("part-*.json"):
        path.unlink()
    for index in range(0, len(rows), 50):
        write_json(folder / f"part-{index // 50 + 1:02d}.json", rows[index:index + 50])


def main():
    for collection, number in TARGETS:
        song = make_song(collection, number)
        update_index(collection, song)
        update_search(collection, song)
        print(collection, number, song["title"])


if __name__ == "__main__":
    main()
