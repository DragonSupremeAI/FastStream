import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {EventEmitter} from '../chrome/player/modules/eventemitter.mjs';

// Load the actual client methods without importing browser-only UI modules.
const source = readFileSync(new URL('../chrome/player/FastStreamClient.mjs', import.meta.url), 'utf8');
const Client = runInNewContext(source.replace(/^import .*;$/gm, '')
    .replace('export class FastStreamClient', 'class FastStreamClient') + '\nFastStreamClient;', {
  EventEmitter,
  EnvUtils: {isSafari: () => false, isWebAudioSupported: () => true},
});

function makeClient(audioContext, play = async () => {}) {
  const calls = [];
  const client = Object.create(Client.prototype);
  Object.assign(client, {
    audioContext,
    player: {play},
    syncedAudioPlayer: {play: async () => calls.push('synced')},
    interfaceController: {play: () => calls.push('ui')},
    audioAnalyzer: {updateBackgroundAnalyzer: () => calls.push('analyzer')},
  });
  return {client, calls};
}

for (const state of ['suspended', 'interrupted']) {
  test(`${state} audio resumes during the play gesture even when video buffers`, async () => {
    let gestureActive = true;
    let resumed = false;
    let startVideo;
    const videoReady = new Promise((resolve) => { startVideo = resolve; });
    const {client, calls} = makeClient({state, resume() {
      assert.equal(gestureActive, true, 'resume must retain user activation');
      resumed = true;
      return Promise.resolve();
    }}, () => {
      assert.equal(gestureActive, true, 'video must also start during the gesture');
      return videoReady;
    });
    const playing = client.play();
    gestureActive = false;
    assert.equal(resumed, true);
    assert.deepEqual(calls, []);
    startVideo();
    await playing;
    assert.deepEqual(calls, ['synced', 'ui', 'analyzer']);
  });
}

test('video starts without waiting for audio resume to settle', async () => {
  let resumeAudio;
  const audioReady = new Promise((resolve) => { resumeAudio = resolve; });
  let started = false;
  const {client} = makeClient({state: 'suspended', resume: () => audioReady}, async () => { started = true; });
  const playing = client.play();
  assert.equal(started, true);
  resumeAudio();
  await playing;
});

test('running or unavailable Web Audio permits normal playback', async () => {
  for (const context of [null, {state: 'running', resume() { assert.fail('already running'); }}]) {
    const {client, calls} = makeClient(context);
    await client.play();
    assert.deepEqual(calls, ['synced', 'ui', 'analyzer']);
  }
});

test('blocked video rejects promptly even while audio resume is pending', async () => {
  const error = new Error('Autoplay blocked');
  const {client, calls} = makeClient({state: 'suspended', resume: () => new Promise(() => {})},
      async () => { throw error; });
  await assert.rejects(client.play(), (actual) => actual === error);
  assert.deepEqual(calls, []);
});

test('audio resume rejection is handled and propagated', async () => {
  const error = new Error('Audio device unavailable');
  const {client} = makeClient({state: 'suspended', resume: async () => { throw error; }});
  await assert.rejects(client.play(), (actual) => actual === error);
});
