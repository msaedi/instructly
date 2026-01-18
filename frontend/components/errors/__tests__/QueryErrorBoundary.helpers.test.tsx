import React, { useEffect } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useErrorHandler } from '../QueryErrorBoundary.helpers';

class TestErrorBoundary extends React.Component<
  { children: React.ReactNode; onError?: (error: Error) => void },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  render() {
    const { error } = this.state;
    if (error) {
      return <div role="alert">{error.message}</div>;
    }
    return this.props.children;
  }
}

function TriggerError({ error }: { error: Error }) {
  const handleError = useErrorHandler();
  return (
    <button type="button" onClick={() => handleError(error)}>
      Trigger
    </button>
  );
}

function HandlerReporter({ onHandler }: { onHandler: (handler: (error: Error) => void) => void }) {
  const handleError = useErrorHandler();
  useEffect(() => {
    onHandler(handleError);
  }, [handleError, onHandler]);
  return null;
}

describe('useErrorHandler', () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders children when no error is triggered', () => {
    render(
      <TestErrorBoundary>
        <TriggerError error={new Error('Boom')} />
      </TestErrorBoundary>
    );

    expect(screen.getByRole('button', { name: 'Trigger' })).toBeInTheDocument();
  });

  it('triggers the error boundary when invoked', async () => {
    const user = userEvent.setup();
    render(
      <TestErrorBoundary>
        <TriggerError error={new Error('Exploded')} />
      </TestErrorBoundary>
    );

    await user.click(screen.getByRole('button', { name: 'Trigger' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Exploded');
  });

  it('forwards the error to the boundary handler', async () => {
    const onError = jest.fn();
    const user = userEvent.setup();

    render(
      <TestErrorBoundary onError={onError}>
        <TriggerError error={new Error('Reported')} />
      </TestErrorBoundary>
    );

    await user.click(screen.getByRole('button', { name: 'Trigger' }));

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Reported' }));
  });

  it('captures different errors after remounting', async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <TestErrorBoundary>
        <TriggerError error={new Error('First')} />
      </TestErrorBoundary>
    );

    await user.click(screen.getByRole('button', { name: 'Trigger' }));
    expect(screen.getByRole('alert')).toHaveTextContent('First');

    unmount();

    render(
      <TestErrorBoundary>
        <TriggerError error={new Error('Second')} />
      </TestErrorBoundary>
    );

    await user.click(screen.getByRole('button', { name: 'Trigger' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Second');
  });

  it('keeps the error handler stable across re-renders', () => {
    const handlers: Array<(error: Error) => void> = [];
    const onHandler = (handler: (error: Error) => void) => handlers.push(handler);

    const { rerender } = render(
      <HandlerReporter onHandler={onHandler} />
    );

    rerender(<HandlerReporter onHandler={(handler) => handlers.push(handler)} />);

    expect(handlers).toHaveLength(2);
    expect(handlers[0]).toBe(handlers[1]);
  });
});
