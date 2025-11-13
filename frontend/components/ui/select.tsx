import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { ChevronDown, ChevronUp, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

type SelectRootProps = React.ComponentPropsWithoutRef<typeof SelectPrimitive.Root>;

export function Select({ onOpenChange, ...rest }: SelectRootProps) {
  return (
    <SelectPrimitive.Root
      {...rest}
      {...(onOpenChange !== undefined ? { onOpenChange } : {})}
    />
  );
}
export const SelectGroup = SelectPrimitive.Group;
export const SelectValue = SelectPrimitive.Value;

type SelectTriggerProps = React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger> & {
  error?: boolean;
  hideIconOnMobile?: boolean;
};

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  SelectTriggerProps
>(({ className, children, error, hideIconOnMobile, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      'w-full inline-flex h-9 items-center justify-between gap-2 rounded-md border bg-white px-3 text-sm text-gray-900 transition-shadow',
      'focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]',
      'data-[state=open]:shadow-[0_0_0_2px_rgba(212,181,240,1)]',
      error ? 'border-red-400' : 'border-gray-300',
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className={cn('h-4 w-4 text-gray-500', hideIconOnMobile && 'hidden sm:block')} />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectScrollUpButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollUpButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpButton ref={ref} className={cn('flex items-center justify-center py-1', className)} {...props}>
    <ChevronUp className="h-4 w-4" />
  </SelectPrimitive.ScrollUpButton>
));
SelectScrollUpButton.displayName = SelectPrimitive.ScrollUpButton.displayName;

const SelectScrollDownButton = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.ScrollDownButton>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownButton>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownButton ref={ref} className={cn('flex items-center justify-center py-1', className)} {...props}>
    <ChevronDown className="h-4 w-4" />
  </SelectPrimitive.ScrollDownButton>
));
SelectScrollDownButton.displayName = SelectPrimitive.ScrollDownButton.displayName;

type SelectContentProps = Omit<
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>,
  'modal' | 'onOpenAutoFocus' | 'onCloseAutoFocus' | 'disableOutsidePointerEvents'
> & {
  position?: 'popper' | 'item-aligned';
};

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  SelectContentProps
>(({ className, children, position = 'popper', style, ...props }, ref) => {
  const sizeStyle =
    position === 'popper'
      ? {
          width: 'var(--radix-select-trigger-width)',
          maxWidth: 'min(var(--radix-select-trigger-width), calc(100vw - 2rem))',
          maxHeight: 'min(18rem, calc(100vh - 4rem))',
        }
      : {
          maxHeight: 'min(18rem, calc(100vh - 4rem))',
        };

  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        ref={ref}
        position={position}
        sideOffset={4}
        collisionPadding={8}
        className={cn(
          'z-50 overflow-hidden rounded-md border border-gray-200 bg-white shadow-md',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          'data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2',
          className
        )}
        style={{ ...sizeStyle, ...style }}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport className="max-h-[18rem] overflow-auto p-1">
          {children}
        </SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
});
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectLabel = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Label ref={ref} className={cn('px-2 py-1.5 text-xs font-medium text-gray-500', className)} {...props} />
));
SelectLabel.displayName = SelectPrimitive.Label.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex w/full cursor-pointer select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none whitespace-nowrap',
      'focus:bg-gray-100 data-[state=checked]:bg-purple-50 data-[state=checked]:text-[#7E22CE]',
      'text-gray-800',
      className
    )}
    {...props}
  >
    <span className="absolute right-2 flex h-4 w-4 items-center justify-center hidden sm:flex">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4 text-[#7E22CE]" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

const SelectSeparator = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Separator>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Separator>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Separator ref={ref} className={cn('my-1 h-px bg-gray-200', className)} {...props} />
));
SelectSeparator.displayName = SelectPrimitive.Separator.displayName;

export { SelectTrigger, SelectContent, SelectItem, SelectLabel, SelectSeparator };
