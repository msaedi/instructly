/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
  SelectValue,
} from '../select';

// Radix relies on pointer capture APIs that jsdom does not provide
Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
  value: jest.fn().mockReturnValue(false),
  writable: true,
});
Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  value: jest.fn(),
  writable: true,
});

describe('Select component — branch coverage', () => {
  // ---- onOpenChange prop ----

  describe('onOpenChange forwarding', () => {
    it('calls onOpenChange when the dropdown opens', async () => {
      const user = userEvent.setup();
      const onOpenChange = jest.fn();

      render(
        <Select onOpenChange={onOpenChange}>
          <SelectTrigger>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      await user.click(screen.getByRole('combobox'));

      await waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(true);
      });
    });

    it('renders without onOpenChange (undefined path)', () => {
      render(
        <Select>
          <SelectTrigger>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });
  });

  // ---- error prop on SelectTrigger ----

  describe('SelectTrigger error prop', () => {
    it('applies border-red-400 class when error is true', () => {
      render(
        <Select>
          <SelectTrigger error>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole('combobox');
      expect(trigger.className).toContain('border-red-400');
      expect(trigger.className).not.toContain('border-gray-300');
    });

    it('applies border-gray-300 class when error is false', () => {
      render(
        <Select>
          <SelectTrigger error={false}>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole('combobox');
      expect(trigger.className).toContain('border-gray-300');
      expect(trigger.className).not.toContain('border-red-400');
    });

    it('defaults to non-error styling when error prop is omitted', () => {
      render(
        <Select>
          <SelectTrigger>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole('combobox');
      expect(trigger.className).not.toContain('border-red-400');
    });
  });

  // ---- position prop on SelectContent ----

  describe('SelectContent position prop', () => {
    it('renders with default position "popper" and applies trigger-width style', async () => {
      render(
        <Select defaultOpen value="a">
          <SelectTrigger>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
            <SelectItem value="b">Beta</SelectItem>
          </SelectContent>
        </Select>
      );

      // When defaultOpen + value is set, text appears in trigger AND dropdown
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Alpha' })).toBeInTheDocument();
      });

      // Verify popper wrapper is present
      const popperWrapper = document.querySelector('[data-radix-popper-content-wrapper]');
      expect(popperWrapper).toBeInTheDocument();
    });

    it('renders with position="item-aligned" (no popper wrapper)', async () => {
      render(
        <Select defaultOpen value="a">
          <SelectTrigger>
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent position="item-aligned">
            <SelectItem value="a">Alpha</SelectItem>
            <SelectItem value="b">Beta</SelectItem>
          </SelectContent>
        </Select>
      );

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Alpha' })).toBeInTheDocument();
      });

      // item-aligned does NOT use popper, so no popper wrapper
      const popperWrapper = document.querySelector('[data-radix-popper-content-wrapper]');
      expect(popperWrapper).not.toBeInTheDocument();
    });
  });

  // ---- custom className on subcomponents ----

  describe('className forwarding', () => {
    it('passes custom className to SelectTrigger', () => {
      render(
        <Select>
          <SelectTrigger className="custom-trigger">
            <SelectValue placeholder="Choose" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole('combobox');
      expect(trigger.className).toContain('custom-trigger');
    });
  });
});
