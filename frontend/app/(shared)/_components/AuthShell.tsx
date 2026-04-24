'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import clsx from 'clsx';
import { BRAND } from '@/app/config/brand';

type AuthShellProps = {
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  logoHref?: string;
  logoLabel?: string;
  onLogoClick?: () => void;
  className?: string;
  containerClassName?: string;
  cardClassName?: string;
  headerClassName?: string;
  contentClassName?: string;
};

export function AuthShell({
  children,
  title,
  subtitle,
  logoHref = '/',
  logoLabel = BRAND.name,
  onLogoClick,
  className,
  containerClassName,
  cardClassName,
  headerClassName,
  contentClassName,
}: AuthShellProps) {
  const logoClickProps = onLogoClick ? { onClick: onLogoClick } : {};

  return (
    <div
      className={clsx(
        'min-h-screen px-4 sm:px-6 lg:px-8 flex items-center justify-center',
        className
      )}
    >
      <div className={clsx('w-full sm:max-w-md sm:mx-auto', containerClassName)}>
        <div className="mt-0 sm:mt-4 sm:mx-auto sm:w-full sm:max-w-md">
          <div
            className={clsx(
              'insta-surface-card py-4 md:py-8 px-0 sm:px-10 sm:shadow',
              cardClassName
            )}
          >
            <div className={clsx('text-center mb-1 md:mb-2', headerClassName)}>
              <Link href={logoHref} {...logoClickProps}>
                <h1 className="text-4xl font-bold text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 transition-colors">
                  {logoLabel}
                </h1>
              </Link>
              {(title || subtitle) && (
                <div className="mt-2">
                  {title && (
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      {title}
                    </h2>
                  )}
                  {subtitle && (
                    <p className="text-gray-600 dark:text-gray-300 mt-0.5">
                      {subtitle}
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className={contentClassName}>{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
