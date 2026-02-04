/**
 * @jest-environment jsdom
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

jest.mock('@sentry/nextjs', () => ({
  captureException: jest.fn(),
}));

import GlobalError from '../global-error';

describe('GlobalError', () => {
  it('renders support code when present', () => {
    const error = new Error('boom') as Error & { request_id?: string };
    error.request_id = 'req-abc-123';

    const html = renderToStaticMarkup(<GlobalError error={error} />);

    expect(html.toLowerCase()).toContain('reference code');
    expect(html).toContain('req-abc-123');
  });
});
