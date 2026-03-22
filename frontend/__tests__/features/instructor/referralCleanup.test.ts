/** @jest-environment node */

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

const SOURCE_ROOTS = ['app', 'components', 'features', 'hooks', 'services', '__tests__', 'e2e'];

function collectSourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'generated' || entry.name === '.next') {
        return [];
      }
      return collectSourceFiles(fullPath);
    }

    return fullPath.endsWith('.ts') || fullPath.endsWith('.tsx') ? [fullPath] : [];
  });
}

describe('founding referral cleanup', () => {
  it('removes the founding referral popup component file', () => {
    expect(
      existsSync(path.join(process.cwd(), 'components', 'instructor', 'InstructorReferralPopup.tsx'))
    ).toBe(false);
  });

  it('removes popup references from frontend source files', () => {
    const currentTestFile = path.join(process.cwd(), '__tests__', 'features', 'instructor', 'referralCleanup.test.ts');
    const files = SOURCE_ROOTS.flatMap((root) => collectSourceFiles(path.join(process.cwd(), root)));

    const offenders = files
      .filter((filePath) => filePath !== currentTestFile)
      .filter((filePath) => {
        const contents = readFileSync(filePath, 'utf8');
        return contents.includes('InstructorReferralPopup') || contents.includes('useReferralPopupData');
      })
      .map((filePath) => path.relative(process.cwd(), filePath));

    expect(offenders).toEqual([]);
  });
});
