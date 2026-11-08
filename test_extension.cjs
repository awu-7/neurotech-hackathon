// Execute the actual content script with a simulated YouTube player.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const sent = [];
const player = {currentTime: 10, playbackRate: 1.5, paused: false, ended: false,
    play: () => Promise.resolve()};
const label = {};
let prompt = null;
const parent = {appendChild(element) { prompt = element; }};
const document = {
    body: parent, fullscreenElement: null, addEventListener() {},
    querySelector: () => player,
    getElementById: id => id === 'neurotech-rewind-prompt' ? prompt : label,
    createElement() {
        const buttons = {};
        return {style: {}, addEventListener() {}, remove() { prompt = null; },
            querySelector(id) {
                return buttons[id] ||= {addEventListener(event, callback) { this.click = callback; }};
            }};
    }
};
const context = vm.createContext({URL, Map, console,
    location: {href: 'https://www.youtube.com/watch?v=abcdefghijk'},
    crypto: {randomUUID: () => 'test-id'}, setInterval: () => {},
    document,
    chrome: {runtime: {lastError: null, sendMessage(message, callback) {
        if (message.type === 'saveInterval') { sent.push(message.interval); callback({ok:true}); }
        else callback({ok:true, data:{last_id:0,events:[]}});
    }}}
});
vm.runInContext(fs.readFileSync('chrome_extension/content.js', 'utf8'), context);
vm.runInContext('handleCommand("distracted")', context);
player.currentTime = 30;
vm.runInContext('handleCommand("focused"); handleCommand("focused")', context);
assert.equal(sent.length, 1);
assert.equal(sent[0].start, 10);
assert.equal(sent[0].end, 30);
vm.runInContext('handleCommand("prompt_rewind")', context);
assert.ok(prompt);
prompt.querySelector('#neurotech-rewind-button').click();
assert.equal(prompt, null);
assert.equal(player.currentTime, 10);
assert.equal(player.playbackRate, 1.25);
context.location.href = 'https://www.youtube.com/watch?v=lmnopqrstuv';
vm.runInContext('resetVideo()', context);
assert.equal(player.playbackRate, 1.5);
vm.runInContext('handleCommand("focused")', context);
assert.equal(sent.length, 1);
player.currentTime = 40;
vm.runInContext('handleCommand("distracted")', context);
player.currentTime = 55;
vm.runInContext('handleCommand("focused"); handleCommand("prompt_rewind")', context);
assert.ok(prompt);
prompt.querySelector('#neurotech-continue-button').click();
assert.equal(prompt, null);
assert.equal(player.currentTime, 55);
assert.equal(sent.length, 2);
vm.runInContext('handleCommand("prompt_rewind")', context);
assert.equal(prompt, null);
vm.runInContext('handleCommand("distracted"); handleCommand("prompt_rewind")', context);
assert.ok(prompt);
context.location.href = 'https://www.youtube.com/watch?v=abcdefghijk';
vm.runInContext('resetVideo()', context);
assert.equal(prompt, null);
player.paused = true;
vm.runInContext('handleCommand("distracted"); handleCommand("focused")', context);
assert.equal(sent.length, 2);
console.log('Extension interval capture, deduplication, replay, navigation, and pause checks passed.');
