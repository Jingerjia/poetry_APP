const collections = { hymns: '\u8a69\u6b4c', supplement: '\u88dc\u5145', 'new-songs': '\u65b0\u6b4c', 'new-poems': '\u65b0\u8a69' };
const $ = (id) => document.getElementById(id);
const indexCache = new Map();
const searchCache = new Map();
let audioIndexPromise = null;
const dbErrorMessage = '\u8cc7\u6599\u5eab\u8f09\u5165\u5931\u6557\uff0c\u8acb\u78ba\u8a8d database/web-db.js \u8207 database \u8cc7\u6599\u593e\u5b58\u5728';

let collection = 'hymns';
let digits = '';
let currentSongs = [];
let currentIndex = 0;
let touchX = 0;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[c]));
}

const variantGroups = [
  ['\u4f60', '\u7962', '\u79b0', '\u88ae', '\u59b3', '\u60a8'],
  ['\u4ed6', '\u7942'],
  ['\u624d', '\u7e94'],
  ['\u5594', '\u54e6'],
  ['\u554a', '\u5475'],
  ['\u4ec0', '\u751a'],
  ['\u88e1', '\u88cf', '\u91cc'],
  ['\u70ba', '\u7232'],
  ['\u8457', '\u7740'],
  ['\u5373', '\u537d'],
  ['\u773e', '\u8846'],
  ['\u771f', '\u771e'],
  ['\u65e2', '\u65e3'],
  ['\u53ea', '\u7947'],
  ['\u5b83', '\u7260'],
  ['\u5403', '\u55ab'],
  ['\u5427', '\u7f77'],
  ['\u9810', '\u8c6b'],
  ['\u555f', '\u5553'],
  ['\u79d8', '\u7955'],
  ['\u5606', '\u6b4e'],
  ['\u8b9a', '\u8d0a'],
  ['\u7fa8', '\u7fa1'],
  ['\u7fa4', '\u7fa3'],
  ['\u6eab', '\u6e29'],
  ['\u5cf0', '\u5cef'],
  ['\u6c61', '\u6c59'],
  ['\u5e8a', '\u7240'],
  ['\u8aaa', '\u8aac'],
  ['\u7d55', '\u7d76'],
  ['\u5f4c', '\u5f25'],
  ['\u9ebc', '\u9ebd', '\u4e48'],
  ['\u537b', '\u5374'],
  ['\u6559', '\u654e'],
  ['\u5b9d', '\u5bf6'],
  ['\u5e76', '\u4e26', '\u4f75'],
];
const variants = Object.fromEntries(variantGroups.flatMap((group) => group.map((char) => [char, group[0]])));

function normalizeText(value) {
  return Array.from(String(value).normalize('NFKC').toLocaleLowerCase())
    .map((char) => variants[char] || char)
    .join('')
    .replace(/[\p{P}\p{S}\p{Z}\s]/gu, '');
}

function normalizedWithMap(value) {
  const chars = Array.from(String(value).normalize('NFKC'));
  let normalized = '';
  const map = [];
  chars.forEach((char, index) => {
    const next = normalizeText(char);
    if (!next) return;
    normalized += next;
    for (let i = 0; i < next.length; i += 1) map.push(index);
  });
  return { chars, normalized, map };
}

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
  if (!indexCache.has(key)) indexCache.set(key, await readJson(`database/indexes/${key}.json`));
  return indexCache.get(key);
}

async function searchRows(key = collection) {
  if (!searchCache.has(key)) {
    const index = await bookIndex(key);
    const shards = await Promise.all(index.searchFiles.map(readJson));
    searchCache.set(key, shards.flat());
  }
  return searchCache.get(key);
}

async function allSearchRows() {
  const books = Object.keys(collections);
  const groups = await Promise.all(books.map(searchRows));
  return groups.flat();
}

async function audioIndex() {
  if (!audioIndexPromise) {
    audioIndexPromise = Promise.resolve().then(async () => {
      if (window.HYMN_DB?.audio) return window.HYMN_DB.audio;
      try {
        return await readJson('database/audio/audio-index.json');
      } catch (error) {
        console.warn('audio index unavailable', error);
        return {};
      }
    });
  }
  return audioIndexPromise;
}

function songButton(song) {
  const snippet = song.snippet ? `<span class="song-snippet">${song.snippet}</span>` : '';
  return `<button class="song-item"><span class="song-number">${displayNumber(song.number)}</span><span class="song-copy"><span class="song-title">${escapeHtml(song.title)}</span><span class="song-book">${collections[song.collection]}</span>${snippet}</span></button>`;
}

function bindSongs(parent, songs) {
  parent.querySelectorAll('.song-item').forEach((button, index) => button.onclick = () => openSong(songs[index], songs));
}

function renderCollections() {
  $('collections').querySelectorAll('.collection').forEach((button) => button.classList.toggle('active', button.dataset.book === collection));
  $('selection-title').textContent = `${collections[collection]} \u9078\u64c7\u8a69\u6b4c`;
}

function updateDisplay() {
  $('number-display').textContent = digits || '\u8f38\u5165\u7de8\u865f';
  $('open-song').disabled = !digits;
}

function pressKey(value) {
  if (value === 'clear') digits = '';
  else if (value === 'extra') digits = digits.startsWith('\u9644') ? digits : '\u9644';
  else if (value === 'delete') digits = digits.slice(0, -1);
  else digits = digits.length < (digits.startsWith('\u9644') ? 3 : 4) ? digits + value : digits;
  updateDisplay();
}

async function selectBook(key) {
  collection = key;
  digits = '';
  renderCollections();
  updateDisplay();
  await loadFeatured();
}

async function loadFeatured() {
  try {
    const songs = (await bookIndex()).songs.slice(0, 9);
    $('featured').innerHTML = songs.map(songButton).join('');
    bindSongs($('featured'), songs);
  } catch (error) {
    console.error(error);
    $('featured').innerHTML = `<p class="empty">${dbErrorMessage}</p>`;
  }
}

async function openByNumber() {
  try {
    const index = await bookIndex();
    const song = index.songs.find((item) => String(item.number) === songNumberInput());
    if (song) openSong(song, index.songs);
    else $('number-display').textContent = '\u627e\u4e0d\u5230\u9019\u9996\u8a69\u6b4c';
  } catch (error) {
    console.error(error);
    $('number-display').textContent = dbErrorMessage;
  }
}

function displayNumber(number) {
  return typeof number === 'number' ? String(number).padStart(3, '0') : String(number);
}

function audioKey(number) {
  return typeof number === 'number' ? String(number).padStart(4, '0') : String(number);
}

function songNumberInput() {
  if (digits.startsWith('\u9644')) return digits;
  return String(Number(digits));
}

function compactLyricText(value) {
  return Array.from(String(value).normalize('NFKC'))
    .filter((char) => /\p{Script=Han}/u.test(char))
    .join('');
}

function searchNeedles(query) {
  const full = normalizeText(query);
  const terms = query.trim().split(/\s+/).map(normalizeText).filter(Boolean);
  return [full, ...terms].filter(Boolean);
}

function songSearchText(song) {
  return song.lyricText || song.text || '';
}

function snippetFor(song, query) {
  const source = song.lyricText || compactLyricText(`${song.title}\n${song.text || ''}`);
  if (!query.trim()) return '';
  const needles = searchNeedles(query);
  const mapped = normalizedWithMap(source);
  const matched = needles
    .map((needle) => ({ needle, index: mapped.normalized.indexOf(needle) }))
    .filter((match) => match.index >= 0)
    .sort((a, b) => b.needle.length - a.needle.length)[0];
  if (!matched) return '';
  const { needle, index } = matched;
  const originalIndex = mapped.map[index] || 0;
  const originalEnd = mapped.map[index + needle.length - 1] ?? originalIndex;
  const start = Math.max(0, originalIndex - 10);
  const end = Math.min(mapped.chars.length, originalEnd + 28);
  const before = mapped.chars.slice(start, originalIndex).join('');
  const hit = mapped.chars.slice(originalIndex, originalEnd + 1).join('');
  const after = mapped.chars.slice(originalEnd + 1, end).join('');
  return `${start ? '\u2026' : ''}${escapeHtml(before)}<mark>${escapeHtml(hit)}</mark>${escapeHtml(after)}${end < mapped.chars.length ? '\u2026' : ''}`;
}

async function search(query = '') {
  try {
    const rows = await allSearchRows();
    const normalizedQuery = normalizeText(query);
    const terms = query.trim().split(/\s+/).map(normalizeText).filter(Boolean);
    const songs = rows
      .map((song) => ({ song, normalized: normalizeText(`${song.number} ${song.title} ${songSearchText(song)}`) }))
      .filter(({ normalized }) => !normalizedQuery || normalized.includes(normalizedQuery) || terms.every((term) => normalized.includes(term)))
      .slice(0, 50)
      .map(({ song }) => ({ ...song, snippet: snippetFor(song, query) }));
    $('search-results').innerHTML = songs.length ? songs.map(songButton).join('') : '<p class="empty">\u6c92\u6709\u7b26\u5408\u7684\u8a69\u6b4c</p>';
    bindSongs($('search-results'), songs);
  } catch (error) {
    console.error(error);
    $('search-results').innerHTML = `<p class="empty">${dbErrorMessage}</p>`;
  }
}

async function toggleSearch(open = $('search').hidden) {
  $('search').hidden = !open;
  if (open) {
    $('search-input').value = '';
    await search();
    $('search-input').focus();
  }
}

async function audioPath(song) {
  if (!['hymns', 'supplement'].includes(song.collection)) return '';
  const audio = await audioIndex();
  return audio[song.collection]?.[audioKey(song.number)] || '';
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '0:00';
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${minutes}:${rest}`;
}

async function resetPlayer(song) {
  const audio = $('audio');
  const path = await audioPath(song);
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  $('audio-progress').value = 0;
  $('audio-current').textContent = '0:00';
  $('audio-duration').textContent = '0:00';
  $('play-toggle').textContent = '\u25b6';
  $('player').hidden = !path;
  if (path) {
    audio.src = path;
    audio.playbackRate = Number($('audio-speed').value);
  }
}

async function renderSong() {
  const song = currentSongs[currentIndex];
  $('viewer-number').textContent = `${collections[song.collection]} ${displayNumber(song.number)}`;
  $('viewer-title').textContent = song.title;
  $('song-page').src = song.images ? song.images[0] : song.image;
  $('page-indicator').textContent = `${currentIndex + 1} / ${currentSongs.length}`;
  $('previous-song').disabled = !currentIndex;
  $('next-song').disabled = currentIndex === currentSongs.length - 1;
  await resetPlayer(song);
}

function openSong(song, songs) {
  currentSongs = songs;
  currentIndex = Math.max(0, songs.findIndex((item) => item.id === song.id));
  $('search').hidden = true;
  $('viewer').hidden = false;
  renderSong();
}

function moveSong(change) {
  const index = currentIndex + change;
  if (index >= 0 && index < currentSongs.length) {
    currentIndex = index;
    renderSong();
  }
}

function bindPlayer() {
  const audio = $('audio');
  $('play-toggle').onclick = async () => {
    if (!audio.src) return;
    if (audio.paused) {
      try { await audio.play(); } catch (error) { console.error(error); $('play-toggle').textContent = '!'; }
    } else {
      audio.pause();
    }
  };
  audio.onplay = () => { $('play-toggle').textContent = '\u275a\u275a'; };
  audio.onpause = () => { $('play-toggle').textContent = '\u25b6'; };
  audio.onerror = () => { $('play-toggle').textContent = '!'; $('audio-duration').textContent = '\u7121\u97f3\u6a94'; };
  audio.onloadedmetadata = () => { $('audio-duration').textContent = formatTime(audio.duration); };
  audio.ontimeupdate = () => {
    $('audio-current').textContent = formatTime(audio.currentTime);
    if (Number.isFinite(audio.duration) && audio.duration > 0) $('audio-progress').value = Math.round((audio.currentTime / audio.duration) * 1000);
  };
  $('audio-progress').oninput = (event) => {
    if (Number.isFinite(audio.duration) && audio.duration > 0) audio.currentTime = (Number(event.target.value) / 1000) * audio.duration;
  };
  $('audio-speed').onchange = (event) => { audio.playbackRate = Number(event.target.value); };
}

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
  $('close-viewer').onclick = () => { $('audio').pause(); $('viewer').hidden = true; };
  $('previous-song').onclick = () => moveSong(-1);
  $('next-song').onclick = () => moveSong(1);
  $('page-area').ontouchstart = (event) => { touchX = event.changedTouches[0].screenX; };
  $('page-area').ontouchend = (event) => { const delta = event.changedTouches[0].screenX - touchX; if (Math.abs(delta) > 55) moveSong(delta > 0 ? -1 : 1); };
  bindPlayer();
}

window.pressKey = pressKey;
window.selectBook = selectBook;
window.openByNumber = openByNumber;
bindUI();
document.addEventListener('keydown', (event) => {
  if (!$('viewer').hidden && event.key === 'ArrowLeft') moveSong(-1);
  if (!$('viewer').hidden && event.key === 'ArrowRight') moveSong(1);
});
renderCollections();
updateDisplay();
loadFeatured().finally(() => { $('loading').hidden = true; });
