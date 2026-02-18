import { readFileSync } from 'fs';
import { resolve } from 'path';

/**
 * Regression test: All auth forms must use method="POST".
 *
 * Without method="POST", a hydration failure (stale cache, JS error, etc.)
 * causes native GET submission, leaking credentials into the URL bar,
 * browser history, and server access logs.
 *
 * If this test fails, add method="POST" to the offending <form> element.
 */

const AUTH_FORM_FILES = [
  'app/(shared)/login/LoginClient.tsx',
  'app/(shared)/signup/page.tsx',
  'app/(shared)/forgot-password/page.tsx',
  'app/(shared)/reset-password/page.tsx',
];

function extractFormTags(source: string): string[] {
  const matches: string[] = [];
  // Match <form with any attributes until >
  const regex = /<form\b[^>]*>/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(source)) !== null) {
    matches.push(match[0]);
  }
  return matches;
}

describe('auth form method="POST" defense', () => {
  it.each(AUTH_FORM_FILES)('%s — every <form> must have method="POST"', (relPath) => {
    const absPath = resolve(__dirname, '../../', relPath);
    const source = readFileSync(absPath, 'utf-8');
    const formTags = extractFormTags(source);

    expect(formTags.length).toBeGreaterThan(0);

    for (const tag of formTags) {
      expect(tag).toMatch(/method=["']POST["']/i);
    }
  });

  it('no auth form files have been removed from the checklist', () => {
    // Guard against someone deleting a file without updating this test
    for (const relPath of AUTH_FORM_FILES) {
      const absPath = resolve(__dirname, '../../', relPath);
      expect(() => readFileSync(absPath, 'utf-8')).not.toThrow();
    }
  });
});
