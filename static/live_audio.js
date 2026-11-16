/* PCM monitoring over authenticated HTTP; no worklet/HTTPS dependency. */
(function (root) {
  'use strict';
  function decodePCM(bytes, channels) {
    const frames = Math.floor(bytes.byteLength / (2 * channels));
    const view = new DataView(bytes.buffer, bytes.byteOffset, frames * channels * 2);
    const output = Array.from({ length: channels }, () => new Float32Array(frames));
    for (let i = 0; i < frames; i++) {
      for (let ch = 0; ch < channels; ch++) output[ch][i] = view.getInt16((i * channels + ch) * 2, true) / 32768;
    }
    return output;
  }
  class PCMPlayer {
    constructor(options) {
      options = options || {};
      this.fetch = options.fetch || (root.fetch && root.fetch.bind(root));
      this.Context = options.AudioContext || root.AudioContext || root.webkitAudioContext;
      this.onState = options.onState || function () {};
      this.volume = .8;
      this.generation = 0;
      this.sources = new Set();
      this.active = false;
    }
    setVolume(value) {
      this.volume = Math.max(0, Math.min(1, Number(value) || 0));
      if (this.gain) this.gain.gain.value = this.volume;
    }
    stop() {
      this.generation++;
      this.active = false;
      if (this.controller) this.controller.abort();
      this.controller = null;
      if (this.reader) this.reader.cancel().catch(function () {});
      this.reader = null;
      for (const source of this.sources) { try { source.stop(); } catch (error) {} }
      this.sources.clear();
      if (this.context) this.context.close().catch(function () {});
      this.context = null;
      this.onState('stopped');
    }
    async start(url) {
      this.stop();
      const generation = this.generation;
      if (!this.Context || !this.fetch) { this.onState('unsupported'); return; }
      this.active = true;
      this.onState('connecting');
      let watchdog;
      try {
        this.context = new this.Context();
        this.gain = this.context.createGain();
        this.gain.gain.value = this.volume;
        this.gain.connect(this.context.destination);
        const controller = new AbortController();
        this.controller = controller;
        watchdog = setTimeout(() => controller.abort(), 12000);
        // resume is called from the user's click before the network request.
        await this.context.resume();
        if (generation !== this.generation) return;
        const response = await this.fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
        clearTimeout(watchdog); watchdog = null;
        if (generation !== this.generation) { if (response.body) await response.body.cancel(); return; }
        if (!response.ok) {
          const error = new Error('Live audio request failed');
          error.state = response.status === 409 ? 'disabled' : (response.status === 401 ? 'login' : 'unavailable');
          throw error;
        }
        this.rate = Number(response.headers.get('X-Audio-Rate'));
        this.channels = Number(response.headers.get('X-Audio-Channels'));
        if (!Number.isFinite(this.rate) || this.rate < 4000 || this.rate > 48000 || ![1, 2].includes(this.channels) || response.headers.get('X-Audio-Format') !== 's16le' || !response.body) {
          throw new Error('Invalid PCM format');
        }
        if (generation !== this.generation) return;
        this.reader = response.body.getReader();
        this.carry = new Uint8Array(0);
        this.nextTime = this.context.currentTime + .06;
        this.onState('playing');
        while (generation === this.generation) {
          const part = await this.reader.read();
          if (part.done) break;
          if (generation === this.generation) this.consume(part.value);
        }
        if (generation === this.generation) this.stop();
      } catch (error) {
        if (generation === this.generation) { this.stop(); this.onState(error.state || 'unavailable'); }
      } finally { if (watchdog) clearTimeout(watchdog); }
    }
    consume(part) {
      const joined = new Uint8Array(this.carry.length + part.length);
      joined.set(this.carry); joined.set(part, this.carry.length);
      const frameBytes = 2 * this.channels;
      const length = joined.length - joined.length % frameBytes;
      this.carry = joined.slice(length);
      if (!length) return;
      // Buffered network data must not turn monitoring into delayed playback.
      const maxBytes = Math.floor(this.rate * .35) * frameBytes;
      const pcm = joined.subarray(Math.max(0, length - maxBytes), length);
      const data = decodePCM(pcm, this.channels);
      if (!data[0].length) return;
      if (this.nextTime - this.context.currentTime > .5) {
        for (const source of this.sources) { try { source.stop(); } catch (error) {} }
        this.sources.clear();
        this.nextTime = this.context.currentTime + .06;
      }
      const buffer = this.context.createBuffer(this.channels, data[0].length, this.rate);
      for (let ch = 0; ch < this.channels; ch++) buffer.getChannelData(ch).set(data[ch]);
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.gain);
      source.onended = () => this.sources.delete(source);
      this.sources.add(source);
      this.nextTime = Math.max(this.nextTime, this.context.currentTime + .03);
      source.start(this.nextTime);
      this.nextTime += buffer.duration;
    }
  }
  const api = { PCMPlayer, decodePCM };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PMCLiveAudio = api;
})(typeof window !== 'undefined' ? window : globalThis);
