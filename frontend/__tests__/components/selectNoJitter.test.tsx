/**
 * Test suite to lock Select component behavior - no jitter on open.
 *
 * Locks the behavior that:
 * - Opening Radix Select does not change document.documentElement.clientWidth
 * - No console warnings for unsupported props (e.g., modal, onOpenAutoFocus)
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '@/components/ui/select';

// Mock methods for jsdom compatibility with Radix UI
Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
  value: jest.fn().mockReturnValue(false),
  writable: true,
});

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  value: jest.fn(),
  writable: true,
});

describe('Select component - no jitter', () => {
  it('does not change document width when opening', async () => {
    const user = userEvent.setup();
    const clientWidthSpy = jest.spyOn(document.documentElement, 'clientWidth', 'get').mockReturnValue(1024);
    document.body.style.paddingRight = '0px';

    try {
      render(
        <Select>
          <SelectTrigger>
            <SelectValue placeholder="Pick one" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="one">One</SelectItem>
            <SelectItem value="two">Two</SelectItem>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole('combobox');
      const widthBefore = document.documentElement.clientWidth;

      await user.click(trigger);

      await waitFor(() => {
        expect(screen.getByText('One')).toBeVisible();
      });

      const widthWhileOpen = document.documentElement.clientWidth;
      expect(widthWhileOpen).toBe(widthBefore);
      expect(clientWidthSpy).toHaveBeenCalled();
      expect(document.body.style.paddingRight).toBe('0px');

      await user.click(screen.getByRole('option', { name: 'One' }));
      await waitFor(() => {
        expect(screen.queryByRole('option', { name: 'Two' })).not.toBeInTheDocument();
      });

      const widthAfter = document.documentElement.clientWidth;
      expect(widthAfter).toBe(widthBefore);
    } finally {
      clientWidthSpy.mockRestore();
      document.body.style.paddingRight = '';
    }
  });

  it('does not emit console warnings for unsupported props', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    render(
      <Select defaultOpen>
        <SelectTrigger>
          <SelectValue placeholder="Pick one" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="one">One</SelectItem>
          <SelectItem value="two">Two</SelectItem>
        </SelectContent>
      </Select>
    );

    // Check for warnings about unsupported props
    const hasModalWarning = (calls: unknown[][]) =>
      calls
        .flat()
        .some((message) =>
          typeof message === 'string' &&
          (message.includes('non-boolean attribute `modal`') ||
           message.includes('modal') ||
           message.includes('onOpenAutoFocus'))
        );

    expect(hasModalWarning(errorSpy.mock.calls)).toBe(false);
    expect(hasModalWarning(warnSpy.mock.calls)).toBe(false);

    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
