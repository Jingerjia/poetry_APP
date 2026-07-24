from pathlib import Path
import json


ROOT = Path("database/songs/blue-poems")
INDEX = Path("database/indexes/blue-poems.json")
SEARCH = Path("database/search/blue-poems")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    title_rows = read_json(Path("blue_titles.json"))
    titles_by_number = {str(row["id"]): str(row["title"]) for row in title_rows}
    titles = {}
    for folder in sorted(ROOT.glob("[0-9][0-9][0-9][0-9]")):
        song_path = folder / "song.json"
        if not song_path.exists():
            continue
        data = read_json(song_path)
        title = titles_by_number.get(str(data.get("number")))
        if not title:
            continue
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
