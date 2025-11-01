import { render } from '@testing-library/react';
import React from 'react';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '@/components/ui/select';

describe('Select component', () => {
  it('does not emit modal attribute warnings when open', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    const widthBefore = document.documentElement.clientWidth;

    render(
      <Select defaultOpen value="one">
        <SelectTrigger>
          <SelectValue placeholder="Pick one" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="one">One</SelectItem>
          <SelectItem value="two">Two</SelectItem>
        </SelectContent>
      </Select>
    );

    const hasModalWarning = (calls: unknown[][]) =>
      calls
        .flat()
        .some((message) => typeof message === 'string' && message.includes('non-boolean attribute `modal`'));
    expect(hasModalWarning(errorSpy.mock.calls)).toBe(false);
    expect(hasModalWarning(warnSpy.mock.calls)).toBe(false);

    expect(document.body.classList.contains('sb-reserve')).toBe(false);
    expect(document.body.style.overflowY).toBe('');
    expect(document.documentElement.clientWidth).toBe(widthBefore);

    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
