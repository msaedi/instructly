export function getPublicProfileLaunchState(studentLaunchEnabled?: boolean | null): {
  isEnabled: boolean;
  title: string;
} {
  const isEnabled = studentLaunchEnabled === true;
  return {
    isEnabled,
    title: isEnabled
      ? 'View your public instructor page'
      : 'Available after student launch',
  };
}
