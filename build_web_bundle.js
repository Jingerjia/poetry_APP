const fs = require("fs");
const path = require("path");

const root = __dirname;
const database = path.join(root, "database");
const books = ["hymns", "supplement", "new-songs", "new-poems"];
const audioBooks = ["hymns", "supplement"];
const bundle = { indexes: {}, search: {}, audio: {} };

for (const book of books) {
  const indexPath = path.join(database, "indexes", `${book}.json`);
  const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
  bundle.indexes[book] = index;
  bundle.search[book] = {};

  for (const searchFile of index.searchFiles) {
    const diskPath = path.join(root, searchFile);
    bundle.search[book][searchFile] = JSON.parse(fs.readFileSync(diskPath, "utf8"));
  }
}

for (const book of audioBooks) {
  const audioDir = path.join(database, "audio", book);
  bundle.audio[book] = {};
  if (!fs.existsSync(audioDir)) continue;

  for (const fileName of fs.readdirSync(audioDir)) {
    if (!fileName.endsWith(".mp3")) continue;
    const number = path.basename(fileName, ".mp3");
    const stats = fs.statSync(path.join(audioDir, fileName));
    if (stats.size > 64000) {
      bundle.audio[book][number] = `database/audio/${book}/${fileName}`;
    }
  }
}

fs.mkdirSync(path.join(database, "audio"), { recursive: true });
fs.writeFileSync(
  path.join(database, "audio", "audio-index.json"),
  JSON.stringify(bundle.audio, null, 2),
  "utf8",
);

const output = [
  "window.HYMN_DB = ",
  JSON.stringify(bundle),
  ";\n",
].join("");

fs.writeFileSync(path.join(database, "web-db.js"), output, "utf8");
console.log(`Wrote ${path.join(database, "web-db.js")}`);
