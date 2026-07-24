const collections = { hymns: '\u8a69\u6b4c', supplement: '\u88dc\u5145', 'new-songs': '\u65b0\u6b4c', 'new-poems': '\u65b0\u8a69', 'blue-poems': '\u85cd\u672c' };
const $ = (id) => document.getElementById(id);
const indexCache = new Map();
const searchCache = new Map();
let audioIndexPromise = null;
const dbErrorMessage = '\u8cc7\u6599\u5eab\u8f09\u5165\u5931\u6557\uff0c\u8acb\u78ba\u8a8d database/web-db.js \u8207 database \u8cc7\u6599\u593e\u5b58\u5728';
const historyKey = 'hymn-library-history-v1';
const favoritesKey = 'hymn-library-favorites-v1';
const playerEnabledKey = 'hymn-library-player-enabled-v1';

let collection = 'hymns';
let browseCollection = 'hymns';
let digits = '';
let currentSongs = [];
let currentIndex = 0;
let currentPageIndex = 0;
let touchX = 0;
let favoriteState = loadFavorites();
let activeFavoriteGroupId = favoriteState.groups[0]?.id || 'default';
let historyTimer = null;
let pendingHistoryId = '';
let setAudioProgress = () => {};
let nativeAudioDuration = 0;
let nativeAudioPlaying = false;
let playerEnabled = readStore(playerEnabledKey, true) !== false;
let activeBrowseGroup = '';
let suppressSaveDialogUntil = 0;
let imageScale = 1;
let imagePanX = 0;
let imagePanY = 0;
let longPressTimer = null;
let touchMode = '';
let pinchStartDistance = 0;
let pinchStartScale = 1;
let dragStartX = 0;
let dragStartY = 0;
let dragStartPanX = 0;
let dragStartPanY = 0;

function hasNativeAudio() {
  return !!window.AndroidBridge?.loadAudio;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[c]));
}

function readStore(key, fallback) {
  if ((key === favoritesKey || key === historyKey || key === playerEnabledKey) && window.AndroidBridge?.readUserStore) {
    try {
      const nativeValue = window.AndroidBridge.readUserStore(key);
      if (nativeValue) return JSON.parse(nativeValue);
    } catch (error) {
      console.warn('native storage read failed', key, error);
    }
  }
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value || fallback;
  } catch (error) {
    console.warn('storage read failed', key, error);
    return fallback;
  }
}

function writeStore(key, value) {
  if ((key === favoritesKey || key === historyKey || key === playerEnabledKey) && window.AndroidBridge?.writeUserStore) {
    try {
      window.AndroidBridge.writeUserStore(key, JSON.stringify(value));
    } catch (error) {
      console.warn('native storage write failed', key, error);
    }
  }
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn('storage write failed', key, error);
  }
}

function songSummary(song) {
  return {
    id: song.id,
    collection: song.collection,
    number: song.number,
    title: song.title,
    image: song.image || song.images?.[0],
    images: song.images,
    data: song.data,
  };
}

function loadHistory() {
  return readStore(historyKey, []);
}

function saveHistory(items) {
  writeStore(historyKey, items.slice(0, 30));
}

function loadFavorites() {
  const fallback = { groups: [{ id: 'default', name: '\u6211\u7684\u6700\u611b', songs: [] }] };
  const state = readStore(favoritesKey, fallback);
  if (!Array.isArray(state.groups) || !state.groups.length) return fallback;
  state.groups = state.groups.map((group) => ({
    id: group.id || `group-${Date.now()}`,
    name: group.name || '\u672a\u547d\u540d',
    songs: Array.isArray(group.songs) ? group.songs : [],
  }));
  return state;
}

function saveFavorites() {
  writeStore(favoritesKey, favoriteState);
}

function normalizeSongList(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((song) => song && song.id && song.collection && song.number !== undefined && song.title)
    .map(songSummary);
}

function normalizeFavoriteState(value) {
  const groups = Array.isArray(value?.groups) ? value.groups : [];
  const normalized = groups
    .filter((group) => group && group.name)
    .map((group, index) => ({
      id: String(group.id || `group-${Date.now().toString(36)}-${index}`),
      name: String(group.name).trim() || '\u672a\u547d\u540d',
      songs: normalizeSongList(group.songs),
    }));
  return { groups: normalized.length ? normalized : [{ id: 'default', name: '\u6211\u7684\u6700\u611b', songs: [] }] };
}

function activeFavoriteGroup() {
  return favoriteState.groups.find((group) => group.id === activeFavoriteGroupId) || favoriteState.groups[0];
}

function rememberSong(song) {
  const summary = songSummary(song);
  const items = [summary, ...loadHistory().filter((item) => item.id !== summary.id)];
  saveHistory(items);
  renderHistory();
}

function cancelHistoryTimer() {
  if (historyTimer) clearTimeout(historyTimer);
  historyTimer = null;
  pendingHistoryId = '';
}

function scheduleHistoryRemember(song) {
  cancelHistoryTimer();
  pendingHistoryId = song.id;
  historyTimer = setTimeout(() => {
    const current = currentSongs[currentIndex];
    if (!$('viewer').hidden && current?.id === pendingHistoryId) rememberSong(current);
    cancelHistoryTimer();
  }, 30000);
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

async function fullSong(song) {
  if (!song || song.images?.length) return song;
  if (song.data) {
    try {
      return { ...song, ...(await readJson(song.data)) };
    } catch (error) {
      console.warn('song detail unavailable', song.data, error);
    }
  }
  try {
    const rows = await searchRows(song.collection);
    const detail = rows.find((item) => item.id === song.id);
    if (detail) return { ...song, ...detail };
  } catch (error) {
    console.warn('song search detail unavailable', song.id, error);
  }
  return song;
}

function renderHistory() {
  const items = loadHistory();
  $('history-list').innerHTML = items.length ? items.map(songButton).join('') : '<p class="empty">\u9084\u6c92\u6709\u958b\u555f\u904e\u8a69\u6b4c</p>';
  bindSongs($('history-list'), items);
}

function showHomePanel(panelId) {
  $('home-tabs').querySelectorAll('.home-tab').forEach((button) => {
    button.classList.toggle('active', button.dataset.panel === panelId);
  });
  document.querySelectorAll('.home-panel').forEach((panel) => {
    panel.hidden = panel.id !== panelId;
  });
}

function closeViewer() {
  cancelHistoryTimer();
  if (window.AndroidBridge?.releaseAudio) window.AndroidBridge.releaseAudio();
  nativeAudioPlaying = false;
  $('audio').pause();
  $('viewer').hidden = true;
}

function appBack() {
  if (!$('group-manager').hidden) {
    closeGroupManager();
    return true;
  }
  if (!$('audio-actions').hidden) {
    closeAudioLibraryMenu();
    return true;
  }
  if (!$('search').hidden) {
    toggleSearch(false);
    return true;
  }
  if (!$('viewer').hidden) {
    closeViewer();
    return true;
  }
  const activePanel = $('home-tabs').querySelector('.home-tab.active')?.dataset.panel;
  if (activePanel && activePanel !== 'keypad-panel') {
    showHomePanel('keypad-panel');
    return true;
  }
  return false;
}

function favoriteRow(song, index) {
  return `<div class="favorite-row">${songButton(song)}<button class="remove-favorite" data-index="${index}" aria-label="remove">\u00d7</button></div>`;
}

function renderFavoriteGroups() {
  const group = activeFavoriteGroup();
  activeFavoriteGroupId = group.id;
  $('favorite-group-jump').innerHTML = favoriteState.groups.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join('');
  $('favorite-group-jump').value = activeFavoriteGroupId;
  $('favorite-groups').innerHTML = favoriteState.groups.map((item) => `<button class="group-chip${item.id === activeFavoriteGroupId ? ' active' : ''}" data-id="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>`).join('');
  $('favorite-groups').querySelectorAll('.group-chip').forEach((button) => {
    button.onclick = () => {
      activeFavoriteGroupId = button.dataset.id;
      renderFavorites();
    };
  });
}

function renderFavoriteList() {
  const group = activeFavoriteGroup();
  $('favorite-list').innerHTML = group.songs.length ? group.songs.map(favoriteRow).join('') : '<p class="empty">\u9019\u500b\u7fa4\u7d44\u9084\u6c92\u6709\u8a69\u6b4c</p>';
  bindSongs($('favorite-list'), group.songs);
  $('favorite-list').querySelectorAll('.remove-favorite').forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      const song = group.songs[Number(button.dataset.index)];
      if (song && !confirm(`\u5f9e\u300c${group.name}\u300d\u79fb\u9664\u300c${song.title}\u300d\uff1f`)) return;
      group.songs.splice(Number(button.dataset.index), 1);
      saveFavorites();
      renderFavorites();
    };
  });
}

function renderManagedGroups() {
  $('managed-groups').innerHTML = favoriteState.groups.map((group, index) => `
    <div class="managed-group">
      <span>${escapeHtml(group.name)}</span>
      <button data-action="up" data-index="${index}" ${index === 0 ? 'disabled' : ''}>\u2191</button>
      <button data-action="down" data-index="${index}" ${index === favoriteState.groups.length - 1 ? 'disabled' : ''}>\u2193</button>
      <button data-action="delete" data-index="${index}" ${favoriteState.groups.length <= 1 ? 'disabled' : ''}>\u522a\u9664</button>
    </div>
  `).join('');
  $('managed-groups').querySelectorAll('button').forEach((button) => {
    button.onclick = () => {
      const index = Number(button.dataset.index);
      const action = button.dataset.action;
      if (action === 'up' && index > 0) {
        [favoriteState.groups[index - 1], favoriteState.groups[index]] = [favoriteState.groups[index], favoriteState.groups[index - 1]];
      } else if (action === 'down' && index < favoriteState.groups.length - 1) {
        [favoriteState.groups[index + 1], favoriteState.groups[index]] = [favoriteState.groups[index], favoriteState.groups[index + 1]];
      } else if (action === 'delete') {
        const target = favoriteState.groups[index];
        if (!target || !confirm(`\u522a\u9664\u7fa4\u7d44\u300c${target.name}\u300d\uff1f\u7fa4\u7d44\u5167\u7684\u6700\u611b\u4e5f\u6703\u4e00\u8d77\u79fb\u9664\u3002`)) return;
        favoriteState.groups.splice(index, 1);
        if (!favoriteState.groups.some((item) => item.id === activeFavoriteGroupId)) activeFavoriteGroupId = favoriteState.groups[0].id;
      }
      saveFavorites();
      renderFavorites();
      renderManagedGroups();
    };
  });
}

function openGroupManager() {
  renderManagedGroups();
  $('group-manager').hidden = false;
}

function closeGroupManager() {
  $('group-manager').hidden = true;
}

function renderFavoriteTools() {
  const group = activeFavoriteGroup();
  const song = currentSongs[currentIndex];
  $('favorite-group-select').innerHTML = favoriteState.groups.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join('');
  $('favorite-group-select').value = group.id;
  const exists = !!song && group.songs.some((item) => item.id === song.id);
  $('toggle-favorite').textContent = exists ? '\u2605' : '\u2606';
  $('toggle-favorite').classList.toggle('active', exists);
  $('toggle-favorite').title = exists ? '\u5f9e\u6700\u611b\u79fb\u9664' : '\u52a0\u5165\u6700\u611b';
}

function renderFavorites() {
  renderFavoriteGroups();
  renderFavoriteList();
  renderFavoriteTools();
}

function addFavoriteGroup() {
  const input = $('new-group-name');
  const name = input.value.trim();
  if (!name) return;
  const id = `group-${Date.now().toString(36)}`;
  favoriteState.groups.push({ id, name, songs: [] });
  activeFavoriteGroupId = id;
  input.value = '';
  saveFavorites();
  renderFavorites();
  renderManagedGroups();
}

function toggleCurrentFavorite() {
  const song = currentSongs[currentIndex];
  if (!song) return;
  const group = activeFavoriteGroup();
  const index = group.songs.findIndex((item) => item.id === song.id);
  if (index >= 0) group.songs.splice(index, 1);
  else group.songs.unshift(songSummary(song));
  saveFavorites();
  renderFavorites();
}

function userDataPayload() {
  return {
    app: 'hymn-library',
    version: 1,
    exportedAt: new Date().toISOString(),
    favorites: normalizeFavoriteState(favoriteState),
  };
}

function hydratePersistentState() {
  favoriteState = loadFavorites();
  activeFavoriteGroupId = favoriteState.groups.some((group) => group.id === activeFavoriteGroupId)
    ? activeFavoriteGroupId
    : favoriteState.groups[0].id;
  playerEnabled = readStore(playerEnabledKey, true) !== false;
}

function exportUserData() {
  const text = JSON.stringify(userDataPayload(), null, 2);
  if (window.AndroidBridge?.exportUserData) {
    window.AndroidBridge.exportUserData(text);
    return;
  }
  const blob = new Blob([text], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'hymn-library-backup.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function applyImportedUserData(text) {
  try {
    const payload = JSON.parse(String(text));
    const importedFavorites = normalizeFavoriteState(payload.favorites || payload);
    if (!confirm('\u532f\u5165\u5f8c\u6703\u8986\u84cb\u76ee\u524d\u9019\u53f0\u88dd\u7f6e\u7684\u6700\u611b\u7fa4\u7d44\uff0c\u6700\u8fd1\u958b\u555f\u4e0d\u6703\u6539\u8b8a\uff0c\u8981\u7e7c\u7e8c\u55ce\uff1f')) return;
    favoriteState = importedFavorites;
    activeFavoriteGroupId = favoriteState.groups[0].id;
    saveFavorites();
    renderFavorites();
    alert('\u532f\u5165\u5b8c\u6210');
  } catch (error) {
    console.error(error);
    alert('\u532f\u5165\u5931\u6557\uff0c\u8acb\u78ba\u8a8d\u662f\u6b63\u78ba\u7684 JSON \u5099\u4efd\u6a94');
  }
}

function importUserData(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => applyImportedUserData(reader.result);
  reader.readAsText(file, 'utf-8');
}

function importUserDataFromText(text) {
  applyImportedUserData(text);
}

function renderCollections() {
  $('collections').querySelectorAll('.collection').forEach((button) => button.classList.toggle('active', button.dataset.book === collection));
  const title = $('selection-title');
  if (title) title.textContent = '\u8a69\u6b4c\u9078\u96c6';
}

function renderBrowseCollections() {
  $('browse-collections').querySelectorAll('.collection').forEach((button) => button.classList.toggle('active', button.dataset.book === browseCollection));
}

function browseGroupLabel(book, start, end, index) {
  if (book === 'hymns') {
    if (start === 1 && end === 52) return '1~52 敬拜父';
    if (start === 53 && end === 127) return '53~127 讚美主1';
    if (start === 128 && end === 194) return '128~194 讚美主2';
  }
  return `${start}~${end}`;
}

function fixedBrowseGroups(book, songs) {
  const numbers = songs.map((song) => Number(song.number)).filter(Number.isFinite);
  if (!numbers.length) return [];
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  const ranges = [];
  if (book === 'hymns') {
    ranges.push([1, 52], [53, 127], [128, 194], [195, 250], [251, 300]);
    for (let start = 301; start <= max; start += 50) ranges.push([start, Math.min(start + 49, max)]);
  } else if (book === 'new-songs') {
    ranges.push([1, 50], [51, 100], [101, 142]);
  } else if (book === 'new-poems') {
    ranges.push([1, 50], [51, 76]);
  } else if (book === 'blue-poems') {
    ranges.push([1, 50], [51, 94]);
  } else if (book === 'supplement') {
    let start = min;
    let previous = min;
    for (const number of numbers.slice(1)) {
      const crossesHundred = Math.floor((previous - 1) / 100) !== Math.floor((number - 1) / 100);
      if (number - previous > 40 || crossesHundred) {
        ranges.push([start, previous]);
        start = number;
      }
      previous = number;
    }
    ranges.push([start, previous]);
  } else {
    for (let start = Math.floor((min - 1) / 100) * 100 + 1; start <= max; start += 100) {
      ranges.push([start, Math.min(start + 99, max)]);
    }
  }
  return ranges
    .map(([start, end], index) => {
      const groupSongs = songs.filter((song) => {
        const number = Number(song.number);
        return number >= start && number <= end;
      });
      return groupSongs.length ? { id: `${start}-${end}`, start, end, label: browseGroupLabel(book, start, end, index), songs: groupSongs } : null;
    })
    .filter(Boolean);
}

function withPreview(song) {
  return { ...song, snippet: previewSnippet(song) };
}

function updateDisplay() {
  $('number-display').textContent = digits || '\u8f38\u5165\u7de8\u865f';
  $('open-song').disabled = !digits;
}

function showNumberMessage(message) {
  digits = '';
  $('number-display').textContent = message;
  $('open-song').disabled = true;
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
    const index = await bookIndex(browseCollection);
    const groups = fixedBrowseGroups(browseCollection, index.songs);
    if (!groups.some((group) => group.id === activeBrowseGroup)) activeBrowseGroup = groups[0]?.id || '';
    $('browse-groups').innerHTML = groups.map((group) => `<button class="group-chip ${group.id === activeBrowseGroup ? 'active' : ''}" data-id="${escapeHtml(group.id)}">${escapeHtml(group.label)}</button>`).join('');
    $('browse-groups').querySelectorAll('button').forEach((button) => {
      button.onclick = () => {
        activeBrowseGroup = button.dataset.id;
        loadFeatured();
      };
    });
    const group = groups.find((item) => item.id === activeBrowseGroup) || groups[0];
    const details = await Promise.all((group?.songs || index.songs).map(fullSong));
    const songs = details.map(withPreview);
    $('featured').innerHTML = songs.map(songButton).join('');
    bindSongs($('featured'), songs);
  } catch (error) {
    console.error(error);
    $('browse-groups').innerHTML = '';
    $('featured').innerHTML = `<p class="empty">${dbErrorMessage}</p>`;
  }
}

async function selectBrowseBook(key) {
  browseCollection = key;
  activeBrowseGroup = '';
  renderBrowseCollections();
  await loadFeatured();
}

async function openByNumber() {
  try {
    const index = await bookIndex();
    const song = index.songs.find((item) => String(item.number) === songNumberInput());
    if (song) openSong(song, index.songs);
    else showNumberMessage('\u627e\u4e0d\u5230\u9019\u9996\u8a69\u6b4c');
  } catch (error) {
    console.error(error);
    showNumberMessage(dbErrorMessage);
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

function previewSnippet(song) {
  const source = song.lyricText || compactLyricText(`${song.title}\n${song.text || ''}`);
  const text = Array.from(source).slice(0, 42).join('');
  return text ? `${escapeHtml(text)}${Array.from(source).length > 42 ? '\u2026' : ''}` : '';
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

async function audioDownloadItems() {
  const audio = await audioIndex();
  return ['hymns', 'supplement'].flatMap((book) => Object.entries(audio[book] || {}).map(([number, path]) => ({
    collection: book,
    number,
    path,
  })));
}

async function updateAudioLibrary() {
  if (!window.AndroidBridge?.downloadMissingAudio) return;
  const ok = confirm('\u662f\u5426\u66f4\u65b0\u97f3\u6a94\uff1f\u5df2\u6709\u7684\u97f3\u6a94\u6703\u81ea\u52d5\u8df3\u904e\u3002');
  if (!ok) return;
  closeAudioLibraryMenu();
  const button = $('audio-library-download');
  button.disabled = true;
  button.textContent = '\u6e96\u5099\u4e2d...';
  try {
    const items = await audioDownloadItems();
    window.AndroidBridge.downloadMissingAudio(JSON.stringify(items));
  } catch (error) {
    console.error(error);
    button.disabled = false;
    button.textContent = '\u4e0b\u8f09\u5931\u6557';
  }
}

function closeAudioLibraryMenu() {
  $('audio-actions').hidden = true;
}

async function showAudioLibraryMenu() {
  if (!window.AndroidBridge?.downloadMissingAudio) return;
  $('audio-actions').hidden = false;
}

function deleteAudioLibrary() {
  if (!window.AndroidBridge?.deleteDownloadedAudio) return;
  if (!confirm('\u78ba\u5b9a\u8981\u522a\u9664\u5df2\u4e0b\u8f09\u7684\u97f3\u6a94\uff1f\u522a\u9664\u5f8c\u9700\u8981\u91cd\u65b0\u4e0b\u8f09\u624d\u80fd\u96e2\u7dda\u64ad\u653e\u3002')) return;
  closeAudioLibraryMenu();
  const button = $('audio-library-download');
  button.disabled = true;
  button.textContent = '\u522a\u9664\u4e2d...';
  window.AndroidBridge.deleteDownloadedAudio();
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
  if (window.AndroidBridge?.releaseAudio) window.AndroidBridge.releaseAudio();
  nativeAudioDuration = 0;
  nativeAudioPlaying = false;
  setAudioProgress(0);
  $('audio-current').textContent = '0:00';
  $('audio-duration').textContent = '0:00';
  $('play-toggle').textContent = '\u25b6';
  $('player').hidden = !path || !playerEnabled;
  renderPlayerToggle();
  if (!playerEnabled) return;
  if (path) {
    if (hasNativeAudio()) {
      nativeAudioDuration = window.AndroidBridge.loadAudio(path, Number($('audio-speed').value));
      if (nativeAudioDuration > 0) $('audio-duration').textContent = formatTime(nativeAudioDuration / 1000);
      else $('audio-duration').textContent = '\u9700\u4e0b\u8f09';
    } else {
      audio.src = path;
      audio.playbackRate = Number($('audio-speed').value);
    }
  }
}

async function renderSong() {
  const song = await fullSong(currentSongs[currentIndex]);
  currentSongs[currentIndex] = song;
  const images = song.images?.length ? song.images : [song.image];
  currentPageIndex = Math.min(currentPageIndex, images.length - 1);
  $('viewer-number').textContent = `${collections[song.collection]} ${displayNumber(song.number)}`;
  $('viewer-title').textContent = song.title;
  $('song-page').src = images[currentPageIndex];
  resetImageZoom();
  $('page-indicator').textContent = images.length > 1
    ? `${currentPageIndex + 1}/${images.length} · ${currentIndex + 1}/${currentSongs.length}`
    : `${currentIndex + 1} / ${currentSongs.length}`;
  $('previous-song').disabled = !currentIndex && currentPageIndex === 0;
  $('next-song').disabled = currentIndex === currentSongs.length - 1 && currentPageIndex === images.length - 1;
  renderFavoriteTools();
  scheduleHistoryRemember(song);
  await resetPlayer(song);
}

function openSong(song, songs) {
  currentSongs = songs;
  currentIndex = Math.max(0, songs.findIndex((item) => item.id === song.id));
  currentPageIndex = 0;
  $('search').hidden = true;
  $('viewer').hidden = false;
  renderSong();
}

async function moveSong(change) {
  const song = await fullSong(currentSongs[currentIndex]);
  currentSongs[currentIndex] = song;
  const images = song?.images?.length ? song.images : [song?.image];
  if (song && change > 0 && currentPageIndex < images.length - 1) {
    currentPageIndex += 1;
    renderSong();
    return;
  }
  if (song && change < 0 && currentPageIndex > 0) {
    currentPageIndex -= 1;
    renderSong();
    return;
  }
  const index = currentIndex + change;
  if (index >= 0 && index < currentSongs.length) {
    currentIndex = index;
    currentPageIndex = change > 0 ? 0 : ((currentSongs[currentIndex].images?.length || 1) - 1);
    renderSong();
  }
}

function renderPlayerToggle() {
  const button = $('toggle-player-enabled');
  button.classList.toggle('active', playerEnabled);
  button.textContent = playerEnabled ? '\u25b6' : '\u25b7';
  button.title = playerEnabled ? '\u95dc\u9589\u64ad\u653e\u5217' : '\u958b\u555f\u64ad\u653e\u5217';
}

async function togglePlayerEnabled() {
  playerEnabled = !playerEnabled;
  writeStore(playerEnabledKey, playerEnabled);
  renderPlayerToggle();
  if (!$('viewer').hidden) await resetPlayer(currentSongs[currentIndex]);
}

function bindPlayer() {
  const audio = $('audio');
  const progress = $('audio-progress');
  const progressFill = $('audio-progress-fill');
  const setProgress = (value) => {
    const clamped = Math.min(1000, Math.max(0, Math.round(Number(value) || 0)));
    progress.dataset.value = String(clamped);
    progress.setAttribute('aria-valuenow', String(clamped));
    progressFill.style.width = `${clamped / 10}%`;
  };
  setAudioProgress = setProgress;
  const seekAudio = (value) => {
    const clamped = Math.min(1000, Math.max(0, Math.round(Number(value) || 0)));
    setProgress(clamped);
    if (hasNativeAudio()) {
      if (!nativeAudioDuration) return;
      const millis = Math.round((clamped / 1000) * nativeAudioDuration);
      window.AndroidBridge.seekAudio(millis);
      $('audio-current').textContent = formatTime(millis / 1000);
      return;
    }
    if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
    const wasPaused = audio.paused;
    audio.currentTime = (clamped / 1000) * audio.duration;
    $('audio-current').textContent = formatTime(audio.currentTime);
    if (wasPaused) audio.pause();
  };
  const pointerX = (event) => event.clientX ?? event.touches?.[0]?.clientX ?? event.changedTouches?.[0]?.clientX;
  const seekFromPointer = (event) => {
    if (hasNativeAudio()) {
      if (!nativeAudioDuration) return;
    } else if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
    const x = pointerX(event);
    if (!Number.isFinite(x)) return;
    const rect = progress.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = Math.min(1, Math.max(0, (x - rect.left) / rect.width));
    const value = Math.round(ratio * 1000);
    seekAudio(value);
  };
  $('play-toggle').onclick = async () => {
    if (hasNativeAudio()) {
      if (!nativeAudioDuration) return;
      if (nativeAudioPlaying) {
        window.AndroidBridge.pauseAudio();
        nativeAudioPlaying = false;
        $('play-toggle').textContent = '\u25b6';
      } else {
        nativeAudioPlaying = !!window.AndroidBridge.playAudio();
        $('play-toggle').textContent = nativeAudioPlaying ? '\u275a\u275a' : '!';
      }
      return;
    }
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
    if (Number.isFinite(audio.duration) && audio.duration > 0) setProgress((audio.currentTime / audio.duration) * 1000);
  };
  progress.onclick = seekFromPointer;
  progress.onpointerdown = (event) => {
    progress.setPointerCapture?.(event.pointerId);
    seekFromPointer(event);
  };
  progress.onpointermove = (event) => {
    if (event.buttons) seekFromPointer(event);
  };
  progress.ontouchstart = (event) => {
    event.preventDefault();
    seekFromPointer(event);
  };
  progress.ontouchmove = (event) => {
    event.preventDefault();
    seekFromPointer(event);
  };
  progress.onkeydown = (event) => {
    const current = Number(progress.dataset.value || 0);
    if (event.key === 'ArrowLeft') seekAudio(current - 20);
    if (event.key === 'ArrowRight') seekAudio(current + 20);
  };
  $('audio-speed').onchange = (event) => {
    const speed = Number(event.target.value);
    if (hasNativeAudio()) window.AndroidBridge.setAudioSpeed(speed);
    else audio.playbackRate = speed;
  };
}

function resetImageZoom() {
  imageScale = 1;
  imagePanX = 0;
  imagePanY = 0;
  const area = $('page-area');
  area.classList.remove('zoomed', 'zooming');
  const img = $('song-page');
  img.style.setProperty('--zoom', '1');
  img.style.setProperty('--pan-x', '0px');
  img.style.setProperty('--pan-y', '0px');
}

function applyImageZoom() {
  const area = $('page-area');
  const img = $('song-page');
  img.style.setProperty('--zoom', String(imageScale));
  img.style.setProperty('--pan-x', `${imagePanX}px`);
  img.style.setProperty('--pan-y', `${imagePanY}px`);
  area.classList.toggle('zoomed', imageScale > 1.02);
}

function touchDistance(touches) {
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.hypot(dx, dy);
}

function clearLongPress() {
  if (longPressTimer) clearTimeout(longPressTimer);
  longPressTimer = null;
}

function currentImagePath() {
  const song = currentSongs[currentIndex];
  const images = song?.images?.length ? song.images : [song?.image];
  return images[currentPageIndex] || '';
}

function currentImageFileName() {
  const song = currentSongs[currentIndex] || {};
  const safeTitle = String(song.title || 'song').replace(/[\\/:*?"<>|]/g, '').slice(0, 40);
  return `${collections[song.collection] || 'song'}-${displayNumber(song.number || '')}-${currentPageIndex + 1}-${safeTitle}.jpg`;
}

function saveCurrentImage() {
  if (Date.now() < suppressSaveDialogUntil) return;
  suppressSaveDialogUntil = Date.now() + 1400;
  const path = currentImagePath();
  if (!path || !confirm('\u662f\u5426\u5132\u5b58\u9019\u5f35\u5716\u7247?')) return;
  if (window.AndroidBridge?.saveImage) {
    window.AndroidBridge.saveImage(path, currentImageFileName());
    return;
  }
  const link = document.createElement('a');
  link.href = path;
  link.download = currentImageFileName();
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function bindImageGestures() {
  const area = $('page-area');
  area.ontouchstart = (event) => {
    clearLongPress();
    if (event.touches.length === 2) {
      touchMode = 'pinch';
      area.classList.add('zooming');
      pinchStartDistance = touchDistance(event.touches);
      pinchStartScale = imageScale;
      event.preventDefault();
      return;
    }
    touchMode = imageScale > 1.02 ? 'pan' : 'swipe';
    touchX = event.changedTouches[0].screenX;
    dragStartX = event.touches[0].clientX;
    dragStartY = event.touches[0].clientY;
    dragStartPanX = imagePanX;
    dragStartPanY = imagePanY;
    longPressTimer = setTimeout(saveCurrentImage, 650);
  };
  area.ontouchmove = (event) => {
    if (event.touches.length === 2 && touchMode === 'pinch') {
      clearLongPress();
      const ratio = touchDistance(event.touches) / Math.max(1, pinchStartDistance);
      imageScale = Math.min(4, Math.max(1, pinchStartScale * ratio));
      if (imageScale <= 1.02) {
        imageScale = 1;
        imagePanX = 0;
        imagePanY = 0;
      }
      applyImageZoom();
      event.preventDefault();
      return;
    }
    if (event.touches.length === 1) {
      const dx = event.touches[0].clientX - dragStartX;
      const dy = event.touches[0].clientY - dragStartY;
      if (Math.hypot(dx, dy) > 10) clearLongPress();
      if (touchMode === 'pan') {
        imagePanX = dragStartPanX + dx;
        imagePanY = dragStartPanY + dy;
        applyImageZoom();
        event.preventDefault();
      }
    }
  };
  area.ontouchend = (event) => {
    clearLongPress();
    area.classList.remove('zooming');
    if (touchMode === 'swipe' && imageScale <= 1.02) {
      const delta = event.changedTouches[0].screenX - touchX;
      if (Math.abs(delta) > 55) moveSong(delta > 0 ? -1 : 1);
    }
    if (event.touches.length === 0) touchMode = '';
  };
  area.oncontextmenu = (event) => {
    event.preventDefault();
    saveCurrentImage();
  };
}

function bindUI() {
  $('home-tabs').querySelectorAll('.home-tab').forEach((button) => {
    button.onclick = () => showHomePanel(button.dataset.panel);
  });
  $('collections').querySelectorAll('.collection').forEach((button) => {
    button.onclick = () => selectBook(button.dataset.book);
  });
  $('browse-collections').querySelectorAll('.collection').forEach((button) => {
    button.onclick = () => selectBrowseBook(button.dataset.book);
  });
  $('keypad').querySelectorAll('button[data-key]').forEach((button) => {
    button.onclick = () => pressKey(button.dataset.key);
  });
  $('open-song').onclick = openByNumber;
  $('browse-all').onclick = () => toggleSearch(true);
  $('search').onclick = (event) => { if (event.target === $('search')) toggleSearch(false); };
  $('clear-history').onclick = () => { saveHistory([]); renderHistory(); };
  $('add-group').onclick = addFavoriteGroup;
  $('new-group-name').onkeydown = (event) => { if (event.key === 'Enter') addFavoriteGroup(); };
  $('manage-groups').onclick = openGroupManager;
  $('close-group-manager').onclick = closeGroupManager;
  $('group-manager').onclick = (event) => { if (event.target === $('group-manager')) closeGroupManager(); };
  $('favorite-group-jump').onchange = (event) => {
    activeFavoriteGroupId = event.target.value;
    renderFavorites();
  };
  $('export-data').onclick = exportUserData;
  $('import-data').onclick = () => {
    if (window.AndroidBridge?.importUserData) window.AndroidBridge.importUserData();
    else $('import-file').click();
  };
  $('import-file').onchange = (event) => {
    importUserData(event.target.files[0]);
    event.target.value = '';
  };
  if (window.AndroidBridge?.downloadMissingAudio) {
    $('audio-library-download').hidden = false;
    $('audio-library-download').onclick = showAudioLibraryMenu;
  }
  $('audio-actions').onclick = (event) => { if (event.target === $('audio-actions')) closeAudioLibraryMenu(); };
  $('download-audio-action').onclick = updateAudioLibrary;
  $('delete-audio-action').onclick = deleteAudioLibrary;
  $('favorite-group-select').onchange = (event) => { activeFavoriteGroupId = event.target.value; renderFavorites(); };
  $('toggle-favorite').onclick = toggleCurrentFavorite;
  $('toggle-player-enabled').onclick = togglePlayerEnabled;
  $('search-toggle').onclick = () => toggleSearch(true);
  $('search-field').onclick = () => toggleSearch(true);
  $('close-search').onclick = () => toggleSearch(false);
  $('search-input').oninput = (event) => search(event.target.value);
  $('close-viewer').onclick = closeViewer;
  $('previous-song').onclick = () => moveSong(-1);
  $('next-song').onclick = () => moveSong(1);
  bindImageGestures();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelHistoryTimer();
    } else if (!$('viewer').hidden) {
      scheduleHistoryRemember(currentSongs[currentIndex]);
    }
  });
  window.addEventListener('pagehide', cancelHistoryTimer);
  bindPlayer();
}

window.pressKey = pressKey;
window.selectBook = selectBook;
window.openByNumber = openByNumber;
window.appBack = appBack;
window.importUserDataFromText = importUserDataFromText;
window.nativeAudioState = (currentMs, durationMs, playing) => {
  nativeAudioDuration = durationMs || nativeAudioDuration;
  nativeAudioPlaying = !!playing;
  $('audio-current').textContent = formatTime((currentMs || 0) / 1000);
  if (nativeAudioDuration > 0) {
    $('audio-duration').textContent = formatTime(nativeAudioDuration / 1000);
    setAudioProgress((currentMs / nativeAudioDuration) * 1000);
  }
  $('play-toggle').textContent = nativeAudioPlaying ? '\u275a\u275a' : '\u25b6';
};
window.nativeAudioEnded = () => {
  nativeAudioPlaying = false;
  $('play-toggle').textContent = '\u25b6';
  setAudioProgress(1000);
};
window.nativeAudioDownloadProgress = (done, total, downloaded, skipped, failed) => {
  const button = $('audio-library-download');
  button.textContent = `${done}/${total} \u5df2\u4e0b\u8f09 ${downloaded} \u8df3\u904e ${skipped}`;
  if (failed) button.textContent += ` \u5931\u6557 ${failed}`;
};
window.nativeAudioDownloadDone = (downloaded, skipped, failed) => {
  const button = $('audio-library-download');
  button.disabled = false;
  button.textContent = failed ? '\u66f4\u65b0\u5b8c\u6210\u6709\u5931\u6557' : '\u97f3\u6a94\u5df2\u66f4\u65b0';
  if (!$('viewer').hidden) resetPlayer(currentSongs[currentIndex]);
  setTimeout(() => { button.textContent = '\u97f3\u6a94'; }, 2200);
};
window.nativeAudioDeleteDone = (deleted, ok) => {
  const button = $('audio-library-download');
  button.disabled = false;
  button.textContent = ok ? `\u5df2\u522a\u9664 ${deleted}` : '\u522a\u9664\u5931\u6557';
  if (!$('viewer').hidden) resetPlayer(currentSongs[currentIndex]);
  setTimeout(() => { button.textContent = '\u97f3\u6a94'; }, 2200);
};
bindUI();
document.addEventListener('keydown', (event) => {
  if (!$('viewer').hidden && event.key === 'ArrowLeft') moveSong(-1);
  if (!$('viewer').hidden && event.key === 'ArrowRight') moveSong(1);
});
hydratePersistentState();
renderCollections();
renderBrowseCollections();
updateDisplay();
renderPlayerToggle();
renderHistory();
renderFavorites();
loadFeatured();
