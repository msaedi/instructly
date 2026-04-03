import { cva } from 'class-variance-authority';

export const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 cursor-pointer',
  {
    variants: {
      variant: {
        default: 'bg-(--color-primary) text-white hover:bg-purple-800 dark:hover:bg-purple-700',
        destructive: 'bg-red-600 text-white',
        outline: 'border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800',
        secondary: 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100',
        ghost: '',
        link: 'text-(--color-primary) underline-offset-4',
        success: 'bg-green-600 text-white',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);
