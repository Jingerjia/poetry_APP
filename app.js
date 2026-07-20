const collections = { hymns: '\u8a69\u6b4c', supplement: '\u88dc\u5145', 'new-songs': '\u65b0\u6b4c', 'new-poems': '\u65b0\u8a69' };
const $ = (id) => document.getElementById(id);
let collection = 'hymns', digits = '', currentSongs = [], currentIndex = 0, touchX = 0;
const indexCache = new Map();
const dbErrorMessage = '\u8cc7\u6599\u5eab\u8f09\u5165\u5931\u6557\uff0c\u8acb\u78ba\u8a8d database/web-db.js \u8207 database \u8cc7\u6599\u593e\u5b58\u5728';

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[c])); }
async function readJson(path) {
  if (window.HYMN_DB) {
    const indexMatch = path.match(/^database\/indexes\/(.+)\.json$/);
    if (indexMatch) return window.HYMN_DB.indexes[indexMatch[1]];
    for (const book of Object.keys(window.HYMN_DB.search)) {
      if (window.HYMN_DB.search[book][path]) return window.HYMN_DB.search[book][path];
    }
  }
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json();
}
async function bookIndex(key = collection) {
  if (!indexCache.has(key)) {
    indexCache.set(key, await readJson(`database/indexes/${key}.json`));
  }
  return indexCache.get(key);
}
function songButton(song) { return `<button class="song-item"><span class="song-number">${String(song.number).padStart(3,'0')}</span><span class="song-copy"><span class="song-title">${escapeHtml(song.title)}</span><span class="song-book">${collections[song.collection]}</span></span></button>`; }
function bindSongs(parent, songs) { parent.querySelectorAll('.song-item').forEach((button, index) => button.onclick = () => openSong(songs[index], songs)); }
function renderCollections() { $('collections').querySelectorAll('.collection').forEach((button) => button.classList.toggle('active', button.dataset.book === collection)); $('selection-title').textContent = `${collections[collection]} \u9078\u64c7\u8a69\u6b4c`; }
function updateDisplay() { $('number-display').textContent = digits || '\u8f38\u5165\u7de8\u865f'; $('open-song').disabled = !digits; }
function pressKey(value) { if (value === 'extra') return; digits = value === 'delete' ? digits.slice(0, -1) : digits.length < 4 ? digits + value : digits; updateDisplay(); }
async function selectBook(key) { collection = key; digits = ''; renderCollections(); updateDisplay(); await loadFeatured(); }
async function loadFeatured() { try { const songs = (await bookIndex()).songs.slice(0, 9); $('featured').innerHTML = songs.map(songButton).join(''); bindSongs($('featured'), songs); } catch (error) { console.error(error); $('featured').innerHTML = `<p class="empty">${dbErrorMessage}</p>`; } }
async function openByNumber() { try { const index = await bookIndex(); const song = index.songs.find((item) => item.number === Number(digits)); if (song) openSong(song, index.songs); else $('number-display').textContent = '\u627e\u4e0d\u5230\u9019\u9996\u8a69\u6b4c'; } catch (error) { console.error(error); $('number-display').textContent = dbErrorMessage; } }
async function search(query = '') { try { const index = await bookIndex(); const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean); const shards = await Promise.all(index.searchFiles.map(readJson)); const songs = shards.flat().filter((song) => terms.every((term) => `${song.number} ${song.title} ${song.text}`.toLocaleLowerCase().includes(term))).slice(0, 50); $('search-results').innerHTML = songs.length ? songs.map(songButton).join('') : '<p class="empty">\u6c92\u6709\u7b26\u5408\u7684\u8a69\u6b4c</p>'; bindSongs($('search-results'), songs); } catch (error) { console.error(error); $('search-results').innerHTML = `<p class="empty">${dbErrorMessage}</p>`; } }
async function toggleSearch(open = $('search').hidden) { $('search').hidden = !open; if (open) { $('search-input').value = ''; await search(); $('search-input').focus(); } }
function openSong(song, songs) { currentSongs = songs; currentIndex = Math.max(0, songs.findIndex((item) => item.id === song.id)); $('search').hidden = true; $('viewer').hidden = false; renderSong(); }
function renderSong() { const song = currentSongs[currentIndex]; $('viewer-number').textContent = `${collections[song.collection]} ${String(song.number).padStart(3,'0')}`; $('viewer-title').textContent = song.title; $('song-page').src = song.images ? song.images[0] : song.image; $('page-indicator').textContent = `${currentIndex + 1} / ${currentSongs.length}`; $('previous-song').disabled = !currentIndex; $('next-song').disabled = currentIndex === currentSongs.length - 1; const type = song.collection === 'hymns' ? 'ch' : song.collection === 'supplement' ? 'ts' : null; $('music-link').hidden = !type; if (type) $('music-link').href = `https://www.hymnal.net/en/hymn/${type}/${song.number}`; }
function moveSong(change) { const index = currentIndex + change; if (index >= 0 && index < currentSongs.length) { currentIndex = index; renderSong(); } }
function bindUI() {
  $('collections').querySelectorAll('.collection').forEach((button) => {
    button.onclick = () => selectBook(button.dataset.book);
  });
  $('keypad').querySelectorAll('button[data-key]').forEach((button) => {
    button.onclick = () => pressKey(button.dataset.key);
  });
  $('open-song').onclick = openByNumber;
  $('browse-all').onclick = () => toggleSearch(true);
  $('search-toggle').onclick = () => toggleSearch(true);
  $('close-search').onclick = () => toggleSearch(false);
  $('search-input').oninput = (event) => search(event.target.value);
  $('close-viewer').onclick = () => { $('viewer').hidden = true; };
  $('previous-song').onclick = () => moveSong(-1);
  $('next-song').onclick = () => moveSong(1);
  $('page-area').ontouchstart = (event) => { touchX = event.changedTouches[0].screenX; };
  $('page-area').ontouchend = (event) => { const delta = event.changedTouches[0].screenX - touchX; if (Math.abs(delta) > 55) moveSong(delta > 0 ? -1 : 1); };
}
window.pressKey = pressKey; window.selectBook = selectBook; window.openByNumber = openByNumber;
bindUI();
document.addEventListener('keydown', (event) => { if (!$('viewer').hidden && event.key === 'ArrowLeft') moveSong(-1); if (!$('viewer').hidden && event.key === 'ArrowRight') moveSong(1); });
renderCollections(); updateDisplay(); loadFeatured().finally(() => { $('loading').hidden = true; });
