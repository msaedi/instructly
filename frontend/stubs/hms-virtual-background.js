// Stub for @100mslive/hms-virtual-background — the real module pulls in effects-sdk
// (3.5 MB ONNX WebAssembly runtime) and TensorFlow packages for virtual backgrounds.
// Virtual background is not used in our HMSPrebuilt integration (settings gear is hidden),
// so this stub prevents the heavy dependencies from being bundled.

export const HMSVirtualBackgroundTypes = Object.freeze({
  BLUR: 'blur',
  NONE: 'none',
  GIF: 'gif',
  IMAGE: 'image',
  VIDEO: 'video',
  CANVAS: 'canvas',
});

export class HMSVirtualBackgroundPlugin {
  constructor() {}
  isSupported() { return false; }
  checkSupport() { return { isSupported: false }; }
  getName() { return 'HMSVirtualBackgroundPlugin'; }
  getPluginType() { return 'VIDEO'; }
  init() { return Promise.resolve(); }
  setBackground() { return Promise.resolve(); }
  getBackground() { return ''; }
  stop() {}
  processVideoFrame() { return Promise.resolve(); }
}

export class HMSVBPlugin {
  constructor() {}
  isSupported() { return false; }
  isBlurSupported() { return false; }
  checkSupport() { return { isSupported: false }; }
  getName() { return 'HMSVBPlugin'; }
  getPluginType() { return 'VIDEO'; }
  init() { return Promise.resolve(); }
  setBackground() { return Promise.resolve(); }
  getBackground() { return ''; }
  stop() {}
  processVideoFrame() { return Promise.resolve(); }
}

export class HMSEffectsPlugin {
  constructor() {}
  getName() { return 'HMSEffectsPlugin'; }
  isSupported() { return false; }
  removeBlur() {}
  removeBackground() {}
  setBlur() {}
  setPreset() { return Promise.resolve(); }
  onResolutionChange() {}
  getPreset() { return 'balanced'; }
  removeEffects() {}
  setBackground() {}
  getBlurAmount() { return 0; }
  getBackground() { return ''; }
  getMetrics() { return {}; }
  apply(stream) { return stream; }
  stop() {}
}

export const EFFECTS_SDK_ASSETS = '';
