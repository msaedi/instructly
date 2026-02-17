// Stub for @mediapipe/selfie_segmentation — the real module uses Closure Compiler
// output (CJS IIFE) that Turbopack cannot statically resolve as ESM.
// Virtual background is not used in our HMSPrebuilt integration, so this stub
// prevents build failures while keeping the rest of roomkit-react functional.
export class SelfieSegmentation {
  constructor() {}
  setOptions() {}
  onResults() {}
  send() { return Promise.resolve(); }
  reset() {}
}
