import { DRAFT_COOKIE_NAME } from '../constants';

export const readDraftCookie = (doc?: Pick<Document, 'cookie'> | null): Record<string, string> => {
  if (!doc) {
    return {};
  }
  try {
    const cookies = doc.cookie.split(';').map((cookie) => cookie.trim());
    const target = cookies.find((cookie) => cookie.startsWith(`${DRAFT_COOKIE_NAME}=`));
    if (!target) return {};
    const raw = decodeURIComponent(target.split('=')[1] ?? '');
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const entries = Object.entries(parsed).filter(([, value]) => typeof value === 'string') as [
        string,
        string,
      ][];
      return Object.fromEntries(entries);
    }
  } catch {
    // ignore malformed storage
  }
  return {};
};

export const writeDraftCookie = (
  draftsByThread: Record<string, string>,
  doc?: Pick<Document, 'cookie'> | null,
): void => {
  if (!doc) {
    return;
  }
  try {
    const filtered = Object.entries(draftsByThread).filter(([, value]) => value !== '');
    if (filtered.length === 0) {
      doc.cookie = `${DRAFT_COOKIE_NAME}=; path=/; max-age=0`;
      return;
    }
    const payload = encodeURIComponent(JSON.stringify(Object.fromEntries(filtered)));
    doc.cookie = `${DRAFT_COOKIE_NAME}=${payload}; path=/; max-age=604800; SameSite=Lax`;
  } catch {
    // ignore storage errors
  }
};
