// Bridge: the driver calls `window.spike(command, args)` from Playwright, and
// this forwards it to the dedicated worker that owns the OPFS handles.
//
// The worker is kept alive for the whole session on purpose — an exclusive sync
// access handle only means something while its owner is still running, and
// several experiments turn on exactly that.

const worker = new Worker(new URL('./worker.mjs', import.meta.url), { type: 'module' });
const pending = new Map();
let nextId = 1;

worker.onmessage = (event) => {
  const { id, ok, result, error } = event.data;
  const entry = pending.get(id);
  if (!entry) return;
  pending.delete(id);
  ok ? entry.resolve(result) : entry.reject(Object.assign(new Error(error.message), error));
};

window.spike = (command, args) => new Promise((resolve, reject) => {
  const id = nextId++;
  pending.set(id, { resolve, reject });
  worker.postMessage({ id, command, args });
});

// A SECOND worker, so "two lanes on one warehouse" can be asked literally.
const rival = new Worker(new URL('./worker.mjs', import.meta.url), { type: 'module' });
const rivalPending = new Map();
let rivalId = 1;
rival.onmessage = (event) => {
  const { id, ok, result, error } = event.data;
  const entry = rivalPending.get(id);
  if (!entry) return;
  rivalPending.delete(id);
  ok ? entry.resolve(result) : entry.reject(Object.assign(new Error(error.message), error));
};
window.rival = (command, args) => new Promise((resolve, reject) => {
  const id = rivalId++;
  rivalPending.set(id, { resolve, reject });
  rival.postMessage({ id, command, args });
});

window.spikeReady = true;
document.getElementById('log').textContent = 'ready';
