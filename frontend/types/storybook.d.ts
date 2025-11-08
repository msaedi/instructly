declare module '@storybook/react' {
  export type Meta<T = unknown> = {
    title: string;
    component: T;
    parameters?: Record<string, unknown>;
    args?: Record<string, unknown>;
  };

  export type StoryObj<T = unknown> = {
    args?: Partial<T>;
    render?: (args: T) => unknown;
  };
}
