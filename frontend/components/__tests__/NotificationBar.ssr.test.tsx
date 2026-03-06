/**
 * @jest-environment node
 */

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
  }),
}));

import React from 'react';
import { renderToString } from 'react-dom/server';
import { NotificationBar } from '../NotificationBar';

describe('NotificationBar SSR', () => {
  it('falls back to an empty dismissed map when window is unavailable', () => {
    expect(() => renderToString(React.createElement(NotificationBar))).not.toThrow();
  });
});
