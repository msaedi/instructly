// frontend/lib/logger.ts

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  [key: string]: any;
}

class Logger {
  private isDevelopment = process.env.NODE_ENV === 'development';
  private isEnabled = process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true';
  
  private logLevels: Record<LogLevel, number> = {
    debug: 0,
    info: 1,
    warn: 2,
    error: 3,
  };
  
  private currentLevel: LogLevel = this.isDevelopment ? 'debug' : 'warn';
  
  private shouldLog(level: LogLevel): boolean {
    if (!this.isEnabled && !this.isDevelopment) return false;
    return this.logLevels[level] >= this.logLevels[this.currentLevel];
  }
  
  private formatMessage(level: LogLevel, message: string, context?: LogContext): string {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level.toUpperCase()}]`;
    
    if (context && Object.keys(context).length > 0) {
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
      const errorContext = {
        ...context,
        ...(error instanceof Error ? {
          errorMessage: error.message,
          errorStack: error.stack,
        } : { error }),
      };
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
    if (this.isDevelopment) {
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
    if (this.isDevelopment) {
      // Use our own timer implementation to avoid conflicts
      this.timers.set(label, performance.now());
    }
  }
  
  timeEnd(label: string): void {
    if (this.isDevelopment) {
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
  }
  
  // Initialize from localStorage if available
  constructor() {
    if (typeof window !== 'undefined') {
      const storedLevel = localStorage.getItem('log-level') as LogLevel;
      if (storedLevel && this.logLevels[storedLevel] !== undefined) {
        this.currentLevel = storedLevel;
      }
    }
  }
}

// Export singleton instance
export const logger = new Logger();

// At the bottom, add this for debugging:
if (typeof window !== 'undefined') {
  (window as any).logger = logger;
  (window as any).setLogLevel = (level: LogLevel) => logger.setLevel(level);
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