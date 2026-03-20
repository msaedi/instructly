import { getTextWidthTabButtonClasses, getTextWidthTabLabelClasses } from '../textWidthTabs';

describe('textWidthTabs', () => {
  it('keeps active tab emphasis on the button text color only', () => {
    expect(getTextWidthTabButtonClasses(true)).toBe('text-[#7E22CE]');
  });

  it('moves the underline onto the label span', () => {
    expect(getTextWidthTabLabelClasses(true)).toContain('border-[#7E22CE]');
    expect(getTextWidthTabLabelClasses(false)).toContain('border-transparent');
  });
});
