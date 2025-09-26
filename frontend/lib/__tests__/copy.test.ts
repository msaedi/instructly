import { copyToClipboard } from '../copy';

describe('copyToClipboard', () => {
  const navAny = navigator as Navigator & {
    clipboard?: Navigator['clipboard'];
  };
  type DocumentWithExec = Document & { execCommand?: typeof document.execCommand };
  let originalClipboard: Navigator['clipboard'] | undefined;
  let originalExecCommand: typeof document.execCommand | undefined;

  beforeEach(() => {
    originalClipboard = navAny.clipboard;
    originalExecCommand = document.execCommand;
  });

  afterEach(() => {
    if (originalClipboard === undefined) {
      Reflect.deleteProperty(navAny as unknown as Record<string, unknown>, 'clipboard');
    } else {
      navAny.clipboard = originalClipboard;
    }
    const docAny = document as DocumentWithExec;
    if (originalExecCommand) {
      docAny.execCommand = originalExecCommand;
    } else {
      Reflect.deleteProperty(docAny as unknown as Record<string, unknown>, 'execCommand');
    }
    jest.restoreAllMocks();
  });

  it('falls back to textarea copy when clipboard API is unavailable', async () => {
    Reflect.deleteProperty(navAny as unknown as Record<string, unknown>, 'clipboard');
    const execSpy = jest.fn().mockReturnValue(true) as typeof document.execCommand;
    (document as DocumentWithExec).execCommand = execSpy;

    const result = await copyToClipboard('beta-link');

    expect(execSpy).toHaveBeenCalledWith('copy');
    expect(result).toBe(true);
  });
});
