'use client';

import React, { Component, ReactNode, ErrorInfo } from 'react';
import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { ApiError, isAuthError, isNetworkError } from '@/lib/react-query/api';
import { logger } from '@/lib/logger';

interface ErrorFallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
}

/**
 * Error fallback component for query errors
 *
 * Displays user-friendly error messages based on error type
 */
function ErrorFallback({ error, resetErrorBoundary }: ErrorFallbackProps) {
  // Determine error type and message
  const getErrorDetails = () => {
    if (isAuthError(error)) {
      return {
        title: 'Authentication Required',
        message: 'Please log in to continue.',
        action: 'Log In',
        actionHref: '/login',
      };
    }

    if (isNetworkError(error)) {
      return {
        title: 'Connection Error',
        message: 'Unable to connect to our servers. Please check your internet connection.',
        action: 'Try Again',
      };
    }

    if (error instanceof ApiError) {
      return {
        title: 'Something went wrong',
        message: error.message || 'An unexpected error occurred.',
        action: 'Try Again',
      };
    }

    return {
      title: 'Unexpected Error',
      message: 'Something went wrong. Please try again.',
      action: 'Try Again',
    };
  };

  const { title, message, action, actionHref } = getErrorDetails();

  const handleAction = () => {
    if (actionHref) {
      window.location.href = actionHref;
    } else {
      resetErrorBoundary();
    }
  };

  return (
    <div className="min-h-[400px] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-6 text-center">
        <div className="mb-4">
          <svg
            className="mx-auto h-12 w-12 text-red-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        <h2 className="text-xl font-semibold text-gray-900 mb-2">{title}</h2>
        <p className="text-gray-600 mb-6">{message}</p>

        <button
          onClick={handleAction}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          {action}
        </button>

        {process.env.NODE_ENV === 'development' && (
          <details className="mt-6 text-left">
            <summary className="text-sm text-gray-500 cursor-pointer hover:text-gray-700">
              Error Details (Development Only)
            </summary>
            <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap break-words bg-gray-50 p-2 rounded">
              {error.stack || error.message}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

/**
 * React Query Error Boundary Component
 *
 * This component provides error handling for React Query operations.
 * It catches errors from queries that have `throwOnError: true` set.
 *
 * Features:
 * - Automatic error recovery with reset functionality
 * - User-friendly error messages
 * - Special handling for auth and network errors
 * - Development mode error details
 * - Integrated logging
 *
 * @example
 * ```tsx
 * function App() {
 *   return (
 *     <QueryErrorBoundary>
 *       <Routes>
 *         <Route path="/student/dashboard" element={<Dashboard />} />
 *       </Routes>
 *     </QueryErrorBoundary>
 *   );
 * }
 * ```
 */
export function QueryErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ error, resetErrorBoundary }) => (
            <ErrorFallback error={error} resetErrorBoundary={resetErrorBoundary} />
          )}
        >
          {children}
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

/**
 * Generic error boundary class component
 */
interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackRender: (props: ErrorFallbackProps) => ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error('React Query Error Boundary caught error', error, {
      errorInfo,
      stack: error.stack,
    });
  }

  resetErrorBoundary = () => {
    this.props.onReset?.();
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      return this.props.fallbackRender({
        error: this.state.error,
        resetErrorBoundary: this.resetErrorBoundary,
      });
    }

    return this.props.children;
  }
}

/**
 * Hook to manually trigger error boundary
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const throwError = useErrorHandler();
 *
 *   const handleError = (error: Error) => {
 *     throwError(error);
 *   };
 * }
 * ```
 */
export function useErrorHandler() {
  const [, setError] = React.useState();

  return React.useCallback(
    (error: Error) => {
      setError(() => {
        throw error;
      });
    },
    [setError]
  );
}
