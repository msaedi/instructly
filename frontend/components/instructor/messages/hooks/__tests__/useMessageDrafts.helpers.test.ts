import { readDraftCookie, writeDraftCookie } from '../useMessageDrafts.helpers';
import { DRAFT_COOKIE_NAME } from '../../constants';

describe('useMessageDrafts helpers', () => {
  it('returns empty drafts when no document is available', () => {
    expect(readDraftCookie()).toEqual({});
  });

  it('reads only string draft entries from the cookie payload', () => {
    const doc = {
      cookie:
        `other=value; ${DRAFT_COOKIE_NAME}=` +
        encodeURIComponent(JSON.stringify({ a: 'draft', b: 42, c: '' })),
    } as Pick<Document, 'cookie'>;

    expect(readDraftCookie(doc)).toEqual({ a: 'draft', c: '' });
  });

  it('writes and clears draft cookies, and no-ops without a document', () => {
    const doc = { cookie: '' } as Pick<Document, 'cookie'>;

    writeDraftCookie({ thread: 'hello', empty: '' }, doc);
    expect(doc.cookie).toContain(`${DRAFT_COOKIE_NAME}=`);
    expect(doc.cookie).toContain('thread');

    writeDraftCookie({}, doc);
    expect(doc.cookie).toContain('max-age=0');

    expect(() => writeDraftCookie({ thread: 'hello' })).not.toThrow();
  });
});
