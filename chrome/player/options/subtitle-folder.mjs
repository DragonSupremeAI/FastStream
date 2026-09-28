import {LocalSubtitleFolder} from '../ui/subtitles/LocalSubtitleFolder.mjs';
import {NativeSubtitleFolder} from '../ui/subtitles/NativeSubtitleFolder.mjs';

const folder = new LocalSubtitleFolder();
const status = document.getElementById('status');
const choose = document.getElementById('choose');
const reconnect = document.getElementById('reconnect');
const forget = document.getElementById('forget');
const nativePath = document.getElementById('native-path');
const connectNative = document.getElementById('connect-native');
let handle = null;
let backend = 'browser';
document.getElementById('install-command').textContent = `python3 native/install.py --extension-id ${chrome.runtime.id}`;

async function refresh() {
  backend = (await chrome.storage.local.get('localSubtitleBackend')).localSubtitleBackend || 'browser';
  handle = await folder.getHandle();
  document.getElementById('browser-help').hidden = LocalSubtitleFolder.isSupported();
  choose.disabled = !LocalSubtitleFolder.isSupported();
  const state = backend === 'native' ? await NativeSubtitleFolder.request({action: 'status'}) : await folder.getStatus();
  reconnect.hidden = backend === 'native' || state.status !== 'permission-required';
  forget.hidden = state.status === 'unconfigured';
  if (backend === 'native' && state.path) nativePath.value = state.path;
  status.textContent = state.status === 'ready' ? `Connected to ${state.path || state.name}${backend === 'native' ? ' through the local helper' : ''}. Matching subtitles will be added automatically.` :
    state.status === 'permission-required' ? `${state.name} is saved, but Brave needs you to restore access.` : 'No folder selected.';
}

async function run(action) {
  try {
    await action();
    await refresh();
    await chrome.runtime.sendMessage({type: 'LOCAL_SUBTITLE_FOLDER_CHANGED'});
  } catch (error) {
    if (error.name !== 'AbortError') status.textContent = error.message;
  }
}

connectNative.addEventListener('click', () => run(async () => {
  const path = nativePath.value.trim();
  const result = await NativeSubtitleFolder.request(path ? {action: 'configure', path} : {action: 'status'});
  if (result.status !== 'ready') throw new Error('Enter the full path to your SRT folder, then click Save and connect.');
  await chrome.storage.local.set({localSubtitleBackend: 'native'});
}));
choose.addEventListener('click', () => run(async () => {
  await folder.chooseDirectory();
  await chrome.storage.local.set({localSubtitleBackend: 'browser'});
}));
reconnect.addEventListener('click', () => run(async () => {
  if (await handle.requestPermission({mode: 'read'}) !== 'granted') {
    throw new Error('Folder access was not granted. Use Restore folder access to try again.');
  }
}));
forget.addEventListener('click', () => run(async () => {
  if (backend === 'native') await NativeSubtitleFolder.request({action: 'forget'});
  await folder.forget();
  await chrome.storage.local.remove('localSubtitleBackend');
  nativePath.value = '';
}));
refresh().catch((error) => { status.textContent = error.message; });
