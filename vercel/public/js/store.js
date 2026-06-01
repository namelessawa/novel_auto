/**
 * IndexedDB 数据存储层
 * 管理小说、章节和记忆数据的客户端持久化
 */
const DB_NAME = 'NovelAutoDB';
const DB_VERSION = 1;

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('novels')) {
        db.createObjectStore('novels', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('chapters')) {
        const store = db.createObjectStore('chapters', { autoIncrement: true });
        store.createIndex('byNovel', 'novelId', { unique: false });
        store.createIndex('byNovelChapter', ['novelId', 'chapterNum'], { unique: true });
      }
      if (!db.objectStoreNames.contains('memory')) {
        db.createObjectStore('memory', { keyPath: 'novelId' });
      }
    };
    req.onsuccess = (e) => { _db = e.target.result; resolve(_db); };
    req.onerror = (e) => reject(e.target.error);
  });
}

function tx(storeName, mode = 'readonly') {
  return _db.transaction(storeName, mode).objectStore(storeName);
}

function req(idbReq) {
  return new Promise((resolve, reject) => {
    idbReq.onsuccess = () => resolve(idbReq.result);
    idbReq.onerror = () => reject(idbReq.error);
  });
}

// ========== 小说 ==========

async function createNovel(id) {
  const db = await openDB();
  const novel = { id, createdAt: new Date().toISOString() };
  await req(tx('novels', 'readwrite').put(novel));
  // 初始化空记忆
  await req(tx('memory', 'readwrite').put(createEmptyMemory(id)));
  return novel;
}

async function getNovels() {
  await openDB();
  return req(tx('novels').getAll());
}

async function getNovel(id) {
  await openDB();
  return req(tx('novels').get(id));
}

async function deleteNovel(id) {
  await openDB();
  // 删除小说记录
  await req(tx('novels', 'readwrite').delete(id));
  // 删除记忆
  await req(tx('memory', 'readwrite').delete(id));
  // 删除所有章节
  const chapters = await getChapters(id);
  const cTx = _db.transaction('chapters', 'readwrite');
  const cStore = cTx.objectStore('chapters');
  for (const ch of chapters) {
    cStore.delete(ch._key);
  }
  return new Promise((resolve, reject) => {
    cTx.oncomplete = resolve;
    cTx.onerror = () => reject(cTx.error);
  });
}

// ========== 章节 ==========

async function addChapter(novelId, chapterNum, title, content) {
  await openDB();
  const chapter = { novelId, chapterNum, title, content, createdAt: new Date().toISOString() };
  await req(tx('chapters', 'readwrite').add(chapter));
  return chapter;
}

async function getChapters(novelId) {
  await openDB();
  const index = tx('chapters').index('byNovel');
  const all = await req(index.getAll(novelId));
  // 附带 key 用于删除，并按章节号排序
  const store = tx('chapters');
  const withKeys = [];
  return new Promise((resolve, reject) => {
    const cursorReq = store.openCursor();
    cursorReq.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor) {
        if (cursor.value.novelId === novelId) {
          withKeys.push({ ...cursor.value, _key: cursor.key });
        }
        cursor.continue();
      } else {
        withKeys.sort((a, b) => a.chapterNum - b.chapterNum);
        resolve(withKeys);
      }
    };
    cursorReq.onerror = () => reject(cursorReq.error);
  });
}

async function getChapter(novelId, chapterNum) {
  await openDB();
  const index = tx('chapters').index('byNovelChapter');
  return req(index.get([novelId, chapterNum]));
}

// ========== 记忆 ==========

function createEmptyMemory(novelId) {
  return {
    novelId,
    characters: {},
    locations: {},
    worldState: {},
    relationships: {},
    outline: '',
    arcs: [],
    chapterSummaries: [],
    events: [],
  };
}

async function getMemory(novelId) {
  await openDB();
  const mem = await req(tx('memory').get(novelId));
  return mem || createEmptyMemory(novelId);
}

async function updateMemory(novelId, data) {
  await openDB();
  return req(tx('memory', 'readwrite').put({ ...data, novelId }));
}

// ========== 设置 ==========

function getSettings() {
  try {
    return JSON.parse(localStorage.getItem('novelAutoSettings') || '{}');
  } catch { return {}; }
}

function saveSettings(settings) {
  localStorage.setItem('novelAutoSettings', JSON.stringify(settings));
}

function getSetting(key, defaultVal = '') {
  return getSettings()[key] ?? defaultVal;
}

function setSetting(key, value) {
  const s = getSettings();
  s[key] = value;
  saveSettings(s);
}

// ========== 导出下载 ==========

async function exportNovelAsText(novelId) {
  const novel = await getNovel(novelId);
  if (!novel) return null;
  const chapters = await getChapters(novelId);
  if (chapters.length === 0) return null;

  const lines = [`《${novelId}》`, '', `生成时间：${novel.createdAt}`, ''];
  for (const ch of chapters) {
    lines.push('═'.repeat(40));
    lines.push(`${ch.title}`);
    lines.push('═'.repeat(40));
    lines.push('');
    lines.push(ch.content);
    lines.push('');
    lines.push('');
  }
  return lines.join('\n');
}

window.Store = {
  openDB, createNovel, getNovels, getNovel, deleteNovel,
  addChapter, getChapters, getChapter,
  getMemory, updateMemory,
  getSettings, saveSettings, getSetting, setSetting,
  exportNovelAsText,
};
