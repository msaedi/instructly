import { cva } from 'class-variance-authority';

export const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:outline-none',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-(--color-primary) text-white hover:bg-(--color-primary)/80',
        secondary:
          'border-transparent bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 hover:bg-gray-100/80 dark:hover:bg-gray-700/80',
        destructive:
          'border-transparent bg-red-600 text-white hover:bg-red-600/80',
        outline: 'text-gray-900 dark:text-gray-100',
        success: 'border-transparent bg-green-100 text-green-800 hover:bg-green-200 dark:hover:bg-green-800/40',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);
