/**
 * Barrel export test for components/catalog/index.ts (lines 1-2).
 *
 * Verifies that FilterSelectionForm and HomeCatalogCascade are re-exported
 * from the barrel index. Catches broken re-exports when files are renamed.
 */

import * as barrel from '../index';

describe('catalog barrel export (index.ts)', () => {
  it('re-exports FilterSelectionForm', () => {
    expect(barrel.FilterSelectionForm).toBeDefined();
  });

  it('re-exports HomeCatalogCascade', () => {
    expect(barrel.HomeCatalogCascade).toBeDefined();
  });
});
