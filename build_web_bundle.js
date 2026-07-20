const fs = require("fs");
const path = require("path");

const root = __dirname;
const database = path.join(root, "database");
const books = ["hymns", "supplement", "new-songs", "new-poems"];
const bundle = { indexes: {}, search: {} };

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

const output = [
  "window.HYMN_DB = ",
  JSON.stringify(bundle),
  ";\n",
].join("");

fs.writeFileSync(path.join(database, "web-db.js"), output, "utf8");
console.log(`Wrote ${path.join(database, "web-db.js")}`);
