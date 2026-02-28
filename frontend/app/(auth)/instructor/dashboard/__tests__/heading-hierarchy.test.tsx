import fs from 'node:fs';
import path from 'node:path';

describe('Instructor dashboard heading hierarchy guard', () => {
  it('keeps an h2 bridge between dashboard hero h1 and h3 stat headings', () => {
    const source = fs.readFileSync(
      path.join(process.cwd(), 'app/(auth)/instructor/dashboard/page.tsx'),
      'utf8'
    );

    expect(source).toContain('headingAs="h1"');
    expect(source).toContain('<h2 className="sr-only">Overview</h2>');
  });
});
