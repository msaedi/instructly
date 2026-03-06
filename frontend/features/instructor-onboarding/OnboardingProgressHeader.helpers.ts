export const updateWalkerPosition = ({
  container,
  buttons,
  baseIndex,
  setWalkerLeft,
}: {
  container: Pick<HTMLElement, 'getBoundingClientRect'> | null;
  buttons: Array<Pick<HTMLElement, 'getBoundingClientRect'> | null | undefined>;
  baseIndex: number;
  setWalkerLeft: (value: number) => void;
}): boolean => {
  if (!container) {
    return false;
  }
  const button = buttons[baseIndex] ?? buttons[0];
  if (!button) {
    return false;
  }
  const containerRect = container.getBoundingClientRect();
  const targetRect = button.getBoundingClientRect();
  const offset = targetRect.left - containerRect.left + targetRect.width / 2 - 8;
  setWalkerLeft(offset);
  return true;
};
