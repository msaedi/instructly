/**
 * @jest-environment node
 */

import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const frontendRoot = path.resolve(__dirname, '../..');

describe('Trace propagation integration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      ENABLE_OTEL: 'true',
      OTEL_SERVICE_NAME: 'instainstru-web-test',
    };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('injects traceparent header for matching fetch requests', async () => {
    const script = [
      "import { registerOTel } from '@vercel/otel';",
      "let captured = '';",
      'let sawCall = false;',
      'let sawHeaderGetter = false;',
      'const originalFetch = globalThis.fetch;',
      'globalThis.fetch = async (_input, init) => {',
        '  sawCall = true;',
      '  const headers = init?.headers;',
      "  if (headers && typeof headers.get === 'function') {",
      '    sawHeaderGetter = true;',
      "    const candidate = headers.get('traceparent');",
      '    if (candidate) {',
      '      captured = candidate;',
      '    }',
      '  }',
      '  return { status: 200, statusText: \"OK\", headers: new Headers(), body: null };',
      '};',
      'const patterns = [',
      "  new RegExp('^https?://api\\\\.instainstru\\\\.com'),",
      "  new RegExp('^https?://.*\\\\.onrender\\\\.com'),",
      "  new RegExp('^https?://localhost:8000'),",
      '];',
      "const patternMatch = patterns.some((pattern) => pattern.test('https://api.instainstru.com/v1/health'));",
      'registerOTel({',
      "  serviceName: 'instainstru-web-test',",
      '  instrumentationConfig: {',
        '    fetch: {',
      '      propagateContextUrls: patterns,',
      '    },',
      '  },',
      '  spanProcessors: [],',
      '});',
      'const isWrapped = globalThis.fetch !== originalFetch;',
      "await fetch('https://api.instainstru.com/v1/health');",
      'console.log(JSON.stringify({ traceparent: captured, sawCall, sawHeaderGetter, isWrapped, patternMatch }));',
    ].join('\n');

    const { stdout } = await execFileAsync(
      process.execPath,
      ['--input-type=module', '--eval', script],
      {
        cwd: frontendRoot,
        env: {
          ...process.env,
          NODE_OPTIONS: '',
          OTEL_SDK_DISABLED: '',
          OTEL_TRACES_SAMPLER: 'always_on',
        },
      }
    );

    const payload = JSON.parse(stdout.trim() || '{}') as {
      traceparent?: string;
      sawCall?: boolean;
      sawHeaderGetter?: boolean;
      isWrapped?: boolean;
      patternMatch?: boolean;
    };

    expect(payload.isWrapped).toBe(true);
    expect(payload.patternMatch).toBe(true);
    expect(payload.sawCall).toBe(true);
    expect(payload.sawHeaderGetter).toBe(true);
    expect(payload.traceparent).toMatch(/^00-[a-f0-9]{32}-[a-f0-9]{16}-[0-9]{2}$/);
  });
});
