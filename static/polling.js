/* Completion-based polling: at most one task in flight, even on a slow Pi. */
(function (root) {
  'use strict';
  function createPoller(task, interval, shouldRun) {
    let timer = null;
    let active = false;
    let running = false;
    let generation = 0;
    async function tick(token) {
      if (!active || token !== generation) return;
      try {
        if (!running && (!shouldRun || shouldRun())) {
          running = true;
          try { await task(); } finally { running = false; }
        }
      } catch (error) {
        // A temporary network failure must not stop subsequent polls.
      } finally {
        if (active && token === generation) {
          timer = setTimeout(() => tick(token), interval);
        }
      }
    }
    return {
      start() {
        if (active) return;
        active = true;
        tick(++generation);
      },
      stop() {
        active = false;
        generation++;
        clearTimeout(timer);
        timer = null;
      }
    };
  }
  const api = { createPoller };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PKCPolling = api;
})(typeof window !== 'undefined' ? window : globalThis);
