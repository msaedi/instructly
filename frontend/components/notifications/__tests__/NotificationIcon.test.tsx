/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render } from '@testing-library/react';

jest.mock('@/lib/utils', () => ({
  cn: (...classes: (string | boolean | undefined)[]) =>
    classes.filter(Boolean).join(' '),
}));

import { NotificationIcon } from '../NotificationIcon';

describe('NotificationIcon', () => {
  // ---- known categories ----

  it('renders Calendar icon for lesson_updates category', () => {
    const { container } = render(<NotificationIcon category="lesson_updates" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-purple-50');
    expect(span).toHaveClass('text-[#7E22CE]');
    // Icon should be present with aria-hidden
    const icon = container.querySelector('[aria-hidden="true"]');
    expect(icon).toBeInTheDocument();
  });

  it('renders MessageSquare icon for messages category', () => {
    const { container } = render(<NotificationIcon category="messages" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-blue-50');
    expect(span).toHaveClass('text-blue-600');
  });

  it('renders Star icon for reviews category', () => {
    const { container } = render(<NotificationIcon category="reviews" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-emerald-50');
    expect(span).toHaveClass('text-emerald-600');
  });

  it('renders Gift icon for promotional category', () => {
    const { container } = render(<NotificationIcon category="promotional" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-amber-50');
    expect(span).toHaveClass('text-amber-600');
  });

  // ---- fallback (unknown category) - LINE 26 branch ----

  it('renders Bell icon with gray styling for unknown category', () => {
    const { container } = render(<NotificationIcon category="unknown_category" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-gray-100');
    expect(span).toHaveClass('text-gray-600');
    // Should still render an icon
    const icon = container.querySelector('[aria-hidden="true"]');
    expect(icon).toBeInTheDocument();
  });

  it('renders Bell icon with gray styling for empty string category', () => {
    const { container } = render(<NotificationIcon category="" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('bg-gray-100');
    expect(span).toHaveClass('text-gray-600');
  });

  // ---- layout ----

  it('applies common layout classes to the wrapper span', () => {
    const { container } = render(<NotificationIcon category="messages" />);

    const span = container.querySelector('span');
    expect(span).toHaveClass('flex');
    expect(span).toHaveClass('h-9');
    expect(span).toHaveClass('w-9');
    expect(span).toHaveClass('items-center');
    expect(span).toHaveClass('justify-center');
    expect(span).toHaveClass('rounded-full');
  });

  it('renders the icon with h-4 w-4 sizing', () => {
    const { container } = render(<NotificationIcon category="reviews" />);

    const icon = container.querySelector('[aria-hidden="true"]');
    expect(icon).toHaveClass('h-4');
    expect(icon).toHaveClass('w-4');
  });
});
