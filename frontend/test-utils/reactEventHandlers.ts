type ReactPropsRecord = Record<string, unknown>;

const REACT_PROPS_PREFIXES = ['__reactProps$', '__reactEventHandlers$'];
const REACT_FIBER_PREFIXES = ['__reactFiber$', '__reactInternalInstance$'];

const isRecord = (value: unknown): value is ReactPropsRecord =>
  typeof value === 'object' && value !== null;

const readHandlerFromProps = <T extends (...args: never[]) => unknown>(
  props: unknown,
  propName: string,
): T | null => {
  if (!isRecord(props)) return null;
  const handler = props[propName];
  return typeof handler === 'function' ? (handler as T) : null;
};

export const getReactEventHandler = <T extends (...args: never[]) => unknown>(
  element: Element,
  propName: string,
): T => {
  const reactElement = element as unknown as Record<string, unknown>;

  for (const key of Object.keys(reactElement)) {
    if (!REACT_PROPS_PREFIXES.some((prefix) => key.startsWith(prefix))) continue;
    const handler = readHandlerFromProps<T>(reactElement[key], propName);
    if (handler) return handler;
  }

  for (const key of Object.keys(reactElement)) {
    if (!REACT_FIBER_PREFIXES.some((prefix) => key.startsWith(prefix))) continue;
    let fiber: unknown = reactElement[key];
    while (isRecord(fiber)) {
      const handler = readHandlerFromProps<T>(fiber['memoizedProps'], propName);
      if (handler) return handler;
      fiber = fiber['return'];
    }
  }

  throw new Error(`Could not find React handler "${propName}" on element`);
};

export const invokeReactClick = (element: Element, eventOverrides: Record<string, unknown> = {}) => {
  const onClick = getReactEventHandler<(event: Record<string, unknown>) => unknown>(element, 'onClick');
  return onClick({
    currentTarget: element,
    target: element,
    preventDefault() {},
    stopPropagation() {},
    ...eventOverrides,
  });
};
