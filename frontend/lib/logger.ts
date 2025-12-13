// frontend/lib/logger.ts

import { env } from '@/lib/env';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

type LogContext = unknown;

const getDefaultLogLevel = (): LogLevel => {
  if (typeof window !== 'undefined') {
    // Check localStorage first
    const storedLevel = localStorage.getItem('log-level') as LogLevel;
    if (storedLevel && ['debug', 'info', 'warn', 'error'].includes(storedLevel)) {
      return storedLevel;
    }
  }

  // Check environment variable for default level
  const envLevel = env.get('NEXT_PUBLIC_LOG_LEVEL') as LogLevel;
  if (envLevel && ['debug', 'info', 'warn', 'error'].includes(envLevel)) {
    return envLevel;
  }

  // Default based on environment
  if (env.isProduction()) {
    return 'warn'; // Changed from 'info' to be less verbose in production
  }
  return 'debug';
};

class Logger {
  private isDevelopment = env.isDevelopment();
  private isEnabled = env.isTest()
    ? env.get('NEXT_PUBLIC_ENABLE_LOGGING') === 'true'
    : env.get('NEXT_PUBLIC_ENABLE_LOGGING') !== 'false'; // Default to true if not explicitly disabled

  private logLevels: Record<LogLevel, number> = {
    debug: 0,
    info: 1,
    warn: 2,
    error: 3,
  };

  private currentLevel: LogLevel = getDefaultLogLevel();

  private shouldLog(level: LogLevel): boolean {
    // Check if logging is enabled at all
    if (!this.isEnabled) return false;

    // Check if this level should be logged based on current level setting
    return this.logLevels[level] >= this.logLevels[this.currentLevel];
  }

  private formatMessage(level: LogLevel, message: string, context?: LogContext): string {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level.toUpperCase()}]`;

    if (context && typeof context === 'object' && Object.keys(context as Record<string, unknown>).length > 0) {
      return `${prefix} ${message} ${JSON.stringify(context)}`;
    }
    return `${prefix} ${message}`;
  }

  debug(message: string, context?: LogContext): void {
    if (this.shouldLog('debug')) {
      console.log(this.formatMessage('debug', message, context));
    }
  }

  info(message: string, context?: LogContext): void {
    if (this.shouldLog('info')) {
      console.info(this.formatMessage('info', message, context));
    }
  }

  warn(message: string, context?: LogContext): void {
    if (this.shouldLog('warn')) {
      console.warn(this.formatMessage('warn', message, context));
    }
  }

  error(message: string, error?: Error | unknown, context?: LogContext): void {
    if (this.shouldLog('error')) {
      const base: Record<string, unknown> = {};
      if (context && typeof context === 'object') Object.assign(base, context as Record<string, unknown>);
      if (error instanceof Error) {
        base['errorMessage'] = error.message;
        base['errorStack'] = error.stack;
      } else if (typeof error !== 'undefined') {
        base['error'] = error as unknown as Record<string, unknown>;
      }
      const errorContext = base;
      console.error(this.formatMessage('error', message, errorContext));
    }

    // In production, you might want to send this to an error tracking service
    if (!this.isDevelopment && typeof window !== 'undefined') {
      // Example: Sentry, LogRocket, etc.
      // window.Sentry?.captureException(error);
    }
  }

  // Special method for grouping related logs
  group(label: string, fn: () => void): void {
    if (this.shouldLog('debug')) {
      // Only group if debug logging is enabled
      console.group(label);
      fn();
      console.groupEnd();
    } else {
      fn();
    }
  }

  // Performance tracking with safety checks
  private timers = new Map<string, number>();

  time(label: string): void {
    if (this.shouldLog('debug')) {
      // Only time if debug logging is enabled
      // Use our own timer implementation to avoid conflicts
      this.timers.set(label, performance.now());
    }
  }

  timeEnd(label: string): void {
    if (this.shouldLog('debug')) {
      // Only log timing if debug logging is enabled
      const startTime = this.timers.get(label);
      if (startTime) {
        const duration = performance.now() - startTime;
        this.timers.delete(label);
        console.log(`[TIMER] ${label}: ${duration.toFixed(2)}ms`);
      }
    }
  }

  setLevel(level: LogLevel): void {
    this.currentLevel = level;
    if (typeof window !== 'undefined') {
      localStorage.setItem('log-level', level);
    }
    console.log(`[LOGGER] Log level changed to: ${level}`);
  }

  // Method to completely enable/disable logging
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
    console.log(`[LOGGER] Logging ${enabled ? 'enabled' : 'disabled'}`);
  }

  // Get current logger status
  getStatus(): { enabled: boolean; level: LogLevel; isDevelopment: boolean } {
    return {
      enabled: this.isEnabled,
      level: this.currentLevel,
      isDevelopment: this.isDevelopment,
    };
  }

  // Initialize from localStorage if available
  constructor() {
    if (typeof window !== 'undefined') {
      const storedLevel = localStorage.getItem('log-level') as LogLevel;
      if (storedLevel && this.logLevels[storedLevel] !== undefined) {
        this.currentLevel = storedLevel;
      }
    }

    // Log initial status (skip noisy output during unit tests)
    if (!env.isTest()) {
      console.log('[LOGGER] Initialized', {
        enabled: this.isEnabled,
        level: this.currentLevel,
        isDevelopment: this.isDevelopment,
        envVar: env.get('NEXT_PUBLIC_ENABLE_LOGGING'),
      });
    }
  }
}

// Export singleton instance
export const logger = new Logger();

// At the bottom, add this for debugging:
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>)['logger'] = logger;
  (window as unknown as Record<string, unknown>)['setLogLevel'] = (level: LogLevel) => logger.setLevel(level);
  (window as unknown as Record<string, unknown>)['setLoggingEnabled'] = (enabled: boolean) => logger.setEnabled(enabled);
  (window as unknown as Record<string, unknown>)['getLoggerStatus'] = () => logger.getStatus();
}

// Usage examples:
// logger.debug('Clicked booking', { bookingId, userId });
// logger.info('User logged in', { email: user.email });
// logger.warn('API call took too long', { duration: 3000 });
// logger.error('Failed to fetch booking', error, { bookingId });
//
// logger.time('SaveOperation');
// await saveWeekSchedule();
// logger.timeEnd('SaveOperation');
//
// In browser console:
// setLogLevel('warn')  // Only show warnings and errors
// setLoggingEnabled(false)  // Disable all logging
// getLoggerStatus()  // Check current status
