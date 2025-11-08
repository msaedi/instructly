/* eslint-disable @typescript-eslint/no-require-imports */
const budgets = require("./lhci.budgets.json");
/* eslint-enable @typescript-eslint/no-require-imports */

// frontend/lhci.config.js
module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      startServerCommand: "npm run dev-lhci", // next start -p 3100
      url: [
        "http://localhost:3100/",
        "http://localhost:3100/login",
        "http://localhost:3100/lhci/instructor",
        "http://localhost:3100/instructor/availability"
      ],
      settings: {
        // Budgets are enforced during collection
        budgets,
        preset: "desktop",
        formFactor: "desktop",
        screenEmulation: {
          mobile: false,
          width: 1350,
          height: 940,
          deviceScaleFactor: 1,
          disabled: false
        }
      }
    },
    assert: {
      // Start realistic, then ratchet up later as we optimize
      assertions: {
        "categories:performance": ["error", { "minScore": 0.90 }],
        "metrics/total-blocking-time": ["error", { "maxNumericValue": 150, "aggregationMethod": "pessimistic" }],
        "metrics/largest-contentful-paint": ["error", { "maxNumericValue": 2500, "aggregationMethod": "pessimistic" }],
        // Keep as warnings to surface without failing the job
        "uses-long-cache-ttl": "warn",
        "uses-http2": "warn"
      }
    },
    upload: {
      target: "temporary-public-storage"
    }
  }
};
