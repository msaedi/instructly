/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('@sentry/nextjs', () => ({
  captureException: jest.fn(),
}));

import GlobalError from '../global-error';

describe('GlobalError', () => {
  it('renders support code when present', () => {
    const error = new Error('boom') as Error & { request_id?: string };
    error.request_id = 'req-abc-123';

    render(<GlobalError error={error} />);

    expect(screen.getByText(/reference code/i)).toBeInTheDocument();
    expect(screen.getByText('req-abc-123')).toBeInTheDocument();
  });
});
