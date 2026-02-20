// Stub for @100mslive/hms-noise-cancellation — the real module bundles 1.3 MB of
// Krisp audio noise cancellation SDK inline. Noise cancellation is not exposed in
// our HMSPrebuilt integration (settings gear is hidden), so this stub prevents
// the heavy dependency from being bundled.

export class HMSKrispPlugin {
  constructor() {}
  checkSupport() { return { isSupported: false }; }
  setEventBus() {}
  init() { return Promise.resolve(); }
  getPluginType() { return 'AUDIO'; }
  getName() { return 'HMSKrispPlugin'; }
  isSupported() { return false; }
  toggle() {}
  isEnabled() { return false; }
  processAudioTrack(_ctx, source) { return Promise.resolve(source); }
  stop() {}
}
