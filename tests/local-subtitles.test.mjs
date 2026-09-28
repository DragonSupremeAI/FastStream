import test from 'node:test';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {detectSubtitleCode, subtitleLanguage} from '../chrome/player/utils/SubtitleIdentity.mjs';
import {LocalSubtitleFolder} from '../chrome/player/ui/subtitles/LocalSubtitleFolder.mjs';

test('title and filename separators normalize to the same complete code', () => {
  for (const name of ['SSIS-324', 'ssis324', '[SSIS 324]', 'SSIS   324', 'SSIS.324-en.srt', 'SSIS-324_en.srt']) {
    assert.equal(detectSubtitleCode(name), 'SSIS-324', name);
  }
  for (const name of ['SSIS-3245', 'SSIS-32455']) assert.notEqual(detectSubtitleCode(name), 'SSIS-324');
  for (const name of ['ASSISX-324', 'SSIS-324uc4', 'SSIS-324555', 'no code']) assert.equal(detectSubtitleCode(name), null);
  assert.equal(subtitleLanguage('SSIS-324-en (1).srt'), 'en');
  assert.equal(subtitleLanguage('SSIS-324-pt-br.srt'), 'pt-br');
});

function fakeFolder(entries, permission = 'granted') {
  const folder = new LocalSubtitleFolder();
  folder.getHandle = async () => ({name: 'SRT', queryPermission: async () => permission, async *values() { yield* entries; }});
  return folder;
}
function entry(name, text = 'subtitle') {
  return {kind: 'file', name, getFile: async () => ({name, size: text.length, lastModified: 1, text: async () => text})};
}

test('fresh scans find new files, skip other codes and isolate unreadable files', async () => {
  const entries = [entry('SSIS.324-en.srt'), entry('SSIS-3245-en.srt'), entry('SSIS-324.txt'),
    {kind: 'directory', name: 'SSIS-324.srt'}, {kind: 'file', name: 'SSIS-324-fr.srt', getFile: async () => { throw new Error('removed'); }}];
  const folder = fakeFolder(entries);
  let result = await folder.scanForCode('SSIS-324');
  assert.deepEqual(result.files.map((file) => file.name), ['SSIS.324-en.srt']);
  assert.equal(result.errors.length, 1);
  entries.push(entry('SSIS-324_de.srt'));
  result = await folder.scanForCode('SSIS-324');
  assert.equal(result.files.length, 2);
});

test('missing permissions are distinct from no matches and never trigger a prompt', async () => {
  const folder = fakeFolder([], 'prompt');
  assert.equal((await folder.scanForCode('SSIS-324')).status, 'permission-required');
  assert.equal((await folder.getStatus()).status, 'permission-required');
  folder.getHandle = async () => null;
  assert.equal((await folder.scanForCode('SSIS-324')).status, 'unconfigured');
});

test('oversized subtitles do not block a smaller matching subtitle', async () => {
  const big = entry('SSIS-324-fr.srt');
  big.getFile = async () => ({size: 9 * 1024 * 1024});
  const result = await fakeFolder([big, entry('SSIS-324-en.srt')]).scanForCode('SSIS-324');
  assert.equal(result.files.length, 1);
  assert.equal(result.errors.length, 1);
});

test('recognizes screenshot filenames and rejects partial codes', () => {
  const examples = JSON.parse(readFileSync(new URL('./subtitle-code-cases.json', import.meta.url)));
  for (const [filename, expected] of examples) assert.equal(detectSubtitleCode(filename), expected, filename);
});

test('folder scanning includes suffixed releases without matching longer numbers', async () => {
  const result = await fakeFolder([entry('NHDTB-913uc-en.srt'), entry('NHDTB-913.srt'), entry('NHDTB-9130uc-en.srt')]).scanForCode('NHDTB-913');
  assert.deepEqual(result.files.map((file) => file.name).sort(), ['NHDTB-913.srt', 'NHDTB-913uc-en.srt']);
});
