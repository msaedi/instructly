export type ShareOutcome = 'shared' | 'copied' | 'skipped';

export async function shareOrCopy(payload: ShareData, copyText: string): Promise<ShareOutcome> {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return 'skipped';
  }

  const n = navigator as Navigator;
  const canUseWebShare =
    typeof n.share === 'function' && (typeof n.canShare !== 'function' || n.canShare(payload));

  if (canUseWebShare) {
    try {
      await n.share!(payload);
      return 'shared';
    } catch {
      // fall through to copy fallback
    }
  }

  try {
    if (n.clipboard && typeof n.clipboard.writeText === 'function') {
      await n.clipboard.writeText(copyText);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = copyText;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand?.('copy');
      document.body.removeChild(textarea);
    }
    return 'copied';
  } catch {
    return 'skipped';
  }
}
