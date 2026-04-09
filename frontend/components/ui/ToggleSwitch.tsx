type ToggleSwitchProps = {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  ariaLabel?: string;
  title?: string;
  className?: string;
};

export function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
  ariaLabel,
  title,
  className,
}: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-disabled={disabled}
      aria-label={ariaLabel}
      onClick={onChange}
      disabled={disabled}
      title={title}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors motion-reduce:transition-none ${
        checked ? 'bg-(--color-brand-dark)' : 'bg-gray-200 dark:bg-gray-700'
      } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}${className ? ` ${className}` : ''}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white dark:bg-gray-200 shadow transition-transform motion-reduce:transition-none ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
}
