/**
 * Real-time WebAudio Polyphonic Synth + Drum Voice Engine + AnalyserNode tap.
 */

export class WebAudioStudio {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.analyser = null;
    this.delay = null;
    this.delayGain = null;
    this.activeVoices = new Map();
  }

  ensureStarted() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.72;

      const comp = this.ctx.createDynamicsCompressor();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;

      this.delay = this.ctx.createDelay(1.0);
      this.delay.delayTime.value = 0.28;
      const fb = this.ctx.createGain();
      fb.gain.value = 0.28;
      this.delayGain = this.ctx.createGain();
      this.delayGain.gain.value = 0.22;

      this.master.connect(comp);
      this.master.connect(this.delay);
      this.delay.connect(fb);
      fb.connect(this.delay);
      this.delay.connect(this.delayGain);
      this.delayGain.connect(comp);

      comp.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
    return true;
  }

  playSynthNote(midi, patch, durSec = 0.42, gainScale = 0.26) {
    if (!this.ensureStarted()) return;
    const now = this.ctx.currentTime;
    const freq = 440 * Math.pow(2, (midi - 69) / 12);

    this.delay.delayTime.setValueAtTime((patch.delay_ms || 250) / 1000, now);
    this.delayGain.gain.setValueAtTime(patch.delay_mix || 0.18, now);

    const carrier = this.ctx.createOscillator();
    carrier.type = patch.waveform || "sawtooth";
    if (carrier.type === "saw") carrier.type = "sawtooth";
    carrier.frequency.setValueAtTime(freq, now);

    const mod = this.ctx.createOscillator();
    const modGain = this.ctx.createGain();
    mod.frequency.setValueAtTime(freq * (patch.fm_ratio || 2.0), now);
    modGain.gain.setValueAtTime((patch.fm_index || 0) * freq * 0.6, now);
    mod.connect(modGain);
    modGain.connect(carrier.frequency);

    const filter = this.ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(patch.cutoff_hz || 2400, now);
    filter.Q.setValueAtTime(1 + (patch.resonance || 0.2) * 14, now);

    const env = this.ctx.createGain();
    const a = Math.max(0.004, (patch.attack_ms || 12) / 1000);
    const d = Math.max(0.02, (patch.decay_ms || 200) / 1000);
    const s = Math.max(0.02, patch.sustain ?? 0.5);
    const r = Math.max(0.03, (patch.release_ms || 250) / 1000);

    env.gain.setValueAtTime(0.0001, now);
    env.gain.linearRampToValueAtTime(gainScale, now + a);
    env.gain.linearRampToValueAtTime(Math.max(0.01, gainScale * s), now + a + d);
    env.gain.setValueAtTime(Math.max(0.01, gainScale * s), now + durSec);
    env.gain.exponentialRampToValueAtTime(0.0001, now + durSec + r);

    carrier.connect(filter);
    filter.connect(env);
    env.connect(this.master);

    carrier.start(now);
    mod.start(now);
    const stopAt = now + durSec + r + 0.04;
    carrier.stop(stopAt);
    mod.stop(stopAt);
  }

  playKick() {
    if (!this.ensureStarted()) return;
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.frequency.setValueAtTime(150, now);
    osc.frequency.exponentialRampToValueAtTime(44, now + 0.11);
    gain.gain.setValueAtTime(0.85, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.24);
    osc.connect(gain);
    gain.connect(this.master);
    osc.start(now);
    osc.stop(now + 0.25);
  }

  playSnare() {
    if (!this.ensureStarted()) return;
    const now = this.ctx.currentTime;
    const len = Math.floor(this.ctx.sampleRate * 0.16);
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < len; i++) ch[i] = (Math.random() * 2 - 1) * Math.exp(-i / (len * 0.3));
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const hp = this.ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 950;
    const gain = this.ctx.createGain();
    gain.gain.value = 0.45;
    src.connect(hp);
    hp.connect(gain);
    gain.connect(this.master);
    src.start(now);
  }

  playHat() {
    if (!this.ensureStarted()) return;
    const now = this.ctx.currentTime;
    const len = Math.floor(this.ctx.sampleRate * 0.055);
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < len; i++) ch[i] = (Math.random() * 2 - 1) * Math.exp(-i / (len * 0.22));
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    const hp = this.ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 5500;
    const gain = this.ctx.createGain();
    gain.gain.value = 0.25;
    src.connect(hp);
    hp.connect(gain);
    gain.connect(this.master);
    src.start(now);
  }

  readLiveSpectrum(bins = 48) {
    if (!this.analyser) return null;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    let energy = 0;
    for (let i = 0; i < 64; i++) energy += data[i];
    if (energy < 5) return null;
    const out = [];
    const stride = Math.max(1, Math.floor(180 / bins));
    for (let i = 0; i < bins; i++) {
      out.push(data[i * stride] / 255);
    }
    return out;
  }

  readLiveWaveform() {
    if (!this.analyser) return null;
    const data = new Float32Array(256);
    this.analyser.getFloatTimeDomainData(data);
    let peak = 0;
    for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i]));
    return peak > 0.002 ? data : null;
  }
}
