/** @jest-environment node */

import {
  copyToClipboard,
  loadStoredTemplates,
  saveTemplatesToCookie,
} from '../templates';
import { getDefaultTemplates } from '../../constants';

describe('templates in node-like environments', () => {
  it('returns defaults when document is unavailable', () => {
    expect(loadStoredTemplates()).toEqual(getDefaultTemplates());
  });

  it('no-ops when saving without document access', () => {
    expect(() => saveTemplatesToCookie(getDefaultTemplates())).not.toThrow();
  });

  it('returns false when copying without clipboard or document access', async () => {
    await expect(copyToClipboard('test')).resolves.toBe(false);
  });
});
