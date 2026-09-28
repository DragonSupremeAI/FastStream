import {detectSubtitleCode} from '../../utils/SubtitleIdentity.mjs';

export class NativeSubtitleFolder {
  static async request(message) {
    let response;
    try {
      response = await chrome.runtime.sendNativeMessage('org.faststream.subtitles', message);
    } catch (error) {
      throw new Error(`Local subtitle helper is unavailable. Open Local subtitle folder settings to install or reconnect it. (${error.message})`);
    }
    if (!response || response.status === 'error') throw new Error(response?.message || 'No response from subtitle helper.');
    return response;
  }

  async scanForCode(code) {
    if (!code || detectSubtitleCode(code) !== code) {
      return {...await NativeSubtitleFolder.request({action: 'status'}), files: []};
    }
    const result = await NativeSubtitleFolder.request({action: 'scan', code});
    if (result.status !== 'ready') return {...result, files: []};
    const files = [];
    let total = 0;
    for (const entry of result.files) {
      try {
        if (total + entry.size > 24 * 1024 * 1024) throw new Error('Subtitle files exceed the 24 MiB scan limit.');
        total += entry.size;
        const decoder = new TextDecoder();
        let text = '';
        let offset = 0;
        while (true) {
          const chunk = await NativeSubtitleFolder.request({action: 'read', code, name: entry.name, version: entry.version, offset});
          const bytes = Uint8Array.from(atob(chunk.data), (character) => character.charCodeAt(0));
          text += decoder.decode(bytes, {stream: !chunk.done});
          if (chunk.done) break;
          if (chunk.nextOffset <= offset || chunk.nextOffset > entry.size) throw new Error('Invalid subtitle chunk.');
          offset = chunk.nextOffset;
        }
        files.push({name: entry.name, text});
      } catch (error) {
        result.errors.push(`${entry.name}: ${error.message}`);
      }
    }
    return {...result, files};
  }
}
