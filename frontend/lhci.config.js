/* eslint-disable @typescript-eslint/no-require-imports */
const budgets = require("./lhci.budgets.json");
/* eslint-enable @typescript-eslint/no-require-imports */

module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      startServerCommand: "npm run dev-lhci",
      url: [
        "http://localhost:3100/",
        "http://localhost:3100/login",
        "http://localhost:3100/instructors/01J5TESTINSTR0000000000008"
      ],
      settings: {
        budgets
      }
    },
    assert: {
      assertions: {
        "categories:performance": ["error", { minScore: 0.8 }],
        "uses-http2": "warn",
        "uses-long-cache-ttl": "warn"
      }
    },
    upload: {
      target: "temporary-public-storage"
    }
  }
};
