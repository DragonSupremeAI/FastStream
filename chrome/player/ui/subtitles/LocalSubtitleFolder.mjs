import {detectSubtitleCode} from '../../utils/SubtitleIdentity.mjs';

const DATABASE_NAME = 'faststream-local-subtitles';
const STORE_NAME = 'settings';
const HANDLE_KEY = 'directory';
const MAX_FILE_SIZE = 8 * 1024 * 1024;
const MAX_TOTAL_SIZE = 24 * 1024 * 1024;

// Used only by the settings tab and background worker. Embedded players use
// runtime messages so all sites see the same extension-owned directory handle.
export class LocalSubtitleFolder {
  static isSupported() {
    return typeof globalThis.showDirectoryPicker === 'function';
  }

  async chooseDirectory() {
    if (!LocalSubtitleFolder.isSupported()) {
      throw new Error('Enable File System Access API in brave://flags/#file-system-access-api and relaunch Brave first.');
    }
    const handle = await globalThis.showDirectoryPicker({id: 'faststream-subtitles', mode: 'read'});
    await this.saveHandle(handle);
    return handle;
  }

  async getStatus() {
    const handle = await this.getHandle();
    if (!handle) return {status: 'unconfigured'};
    const permission = await handle.queryPermission({mode: 'read'});
    return {status: permission === 'granted' ? 'ready' : 'permission-required', name: handle.name};
  }

  async scanForCode(code) {
    const handle = await this.getHandle();
    if (!handle) return {status: 'unconfigured', files: []};
    if (await handle.queryPermission({mode: 'read'}) !== 'granted') {
      return {status: 'permission-required', name: handle.name, files: []};
    }
    const result = {status: 'ready', name: handle.name, files: [], errors: []};
    if (!code || detectSubtitleCode(code) !== code) return result;
    let totalSize = 0;
    for await (const entry of handle.values()) {
      if (entry.kind !== 'file' || !/\.srt$/i.test(entry.name) || detectSubtitleCode(entry.name) !== code) continue;
      try {
        const file = await entry.getFile();
        if (file.size > MAX_FILE_SIZE || totalSize + file.size > MAX_TOTAL_SIZE) {
          throw new Error('Subtitle files exceed the size limit.');
        }
        totalSize += file.size;
        result.files.push({name: file.name, text: await file.text(), lastModified: file.lastModified});
      } catch (error) {
        result.errors.push(`${entry.name}: ${error.message}`);
      }
    }
    result.files.sort((a, b) => a.name.localeCompare(b.name));
    return result;
  }

  getHandle() {
    return this.withStore('readonly', (store) => store.get(HANDLE_KEY));
  }

  saveHandle(handle) {
    return this.withStore('readwrite', (store) => store.put(handle, HANDLE_KEY));
  }

  forget() {
    return this.withStore('readwrite', (store) => store.delete(HANDLE_KEY));
  }

  async withStore(mode, operation) {
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, mode);
        const request = operation(transaction.objectStore(STORE_NAME));
        transaction.oncomplete = () => resolve(request.result || null);
        transaction.onerror = () => reject(transaction.error || request.error);
        transaction.onabort = () => reject(transaction.error || new Error('Folder setting could not be saved.'));
      });
    } finally {
      db.close();
    }
  }
}
