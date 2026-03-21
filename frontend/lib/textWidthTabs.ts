export function getTextWidthTabButtonClasses(isActive: boolean): string {
  return isActive
    ? 'text-[#7E22CE]'
    : 'text-gray-600 dark:text-gray-400 hover:text-purple-900 dark:hover:text-purple-300';
}

export function getTextWidthTabLabelClasses(isActive: boolean): string {
  return `inline-block border-b-2 pb-1 ${isActive ? 'border-[#7E22CE]' : 'border-transparent'}`;
}
