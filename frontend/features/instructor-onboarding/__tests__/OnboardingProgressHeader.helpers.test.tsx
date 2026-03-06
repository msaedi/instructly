import { updateWalkerPosition } from '../OnboardingProgressHeader.helpers';

describe('OnboardingProgressHeader helpers', () => {
  it('returns false when the progress container or button is missing', () => {
    const setWalkerLeft = jest.fn();

    expect(
      updateWalkerPosition({
        container: null,
        buttons: [],
        baseIndex: 0,
        setWalkerLeft,
      }),
    ).toBe(false);

    expect(
      updateWalkerPosition({
        container: { getBoundingClientRect: () => ({ left: 0, width: 100 } as DOMRect) },
        buttons: [],
        baseIndex: 1,
        setWalkerLeft,
      }),
    ).toBe(false);

    expect(setWalkerLeft).not.toHaveBeenCalled();
  });

  it('computes the walker offset from the selected step button', () => {
    const setWalkerLeft = jest.fn();

    expect(
      updateWalkerPosition({
        container: { getBoundingClientRect: () => ({ left: 20, width: 300 } as DOMRect) },
        buttons: [
          { getBoundingClientRect: () => ({ left: 40, width: 60 } as DOMRect) },
          { getBoundingClientRect: () => ({ left: 120, width: 80 } as DOMRect) },
        ],
        baseIndex: 1,
        setWalkerLeft,
      }),
    ).toBe(true);

    expect(setWalkerLeft).toHaveBeenCalledWith(132);
  });
});
