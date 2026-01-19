import React from 'react';
import { render, screen } from '@testing-library/react';
import Reveal from '../Reveal';
import { useReducedMotion } from 'motion/react';

jest.mock('motion/react', () => {
  const React = require('react');
  type MotionProps = React.PropsWithChildren<{
    initial?: unknown;
    animate?: unknown;
    transition?: unknown;
  }> &
    Record<string, unknown>;
  const createMotion = (Tag: string) =>
    function MotionTag({ children, initial, animate, transition, ...rest }: MotionProps) {
      return React.createElement(
        Tag,
        {
          ...rest,
          'data-initial': JSON.stringify(initial),
          'data-animate': JSON.stringify(animate),
          'data-transition': JSON.stringify(transition),
        },
        children
      );
    };
  return {
    m: {
      div: createMotion('div'),
      section: createMotion('section'),
      article: createMotion('article'),
      span: createMotion('span'),
    },
    useReducedMotion: jest.fn(),
  };
});

const useReducedMotionMock = useReducedMotion as jest.Mock;

describe('Reveal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a static tag when reduced motion is preferred', () => {
    useReducedMotionMock.mockReturnValue(true);
    render(<Reveal as="section">Content</Reveal>);

    const section = screen.getByText('Content');
    expect(section.tagName.toLowerCase()).toBe('section');
  });

  it('renders motion props when reduced motion is not preferred', () => {
    useReducedMotionMock.mockReturnValue(false);
    render(<Reveal>Content</Reveal>);

    const wrapper = screen.getByText('Content');
    expect(wrapper.getAttribute('data-initial')).toContain('"opacity":0');
    expect(wrapper.getAttribute('data-animate')).toContain('"opacity":1');
  });

  it('uses custom delay and y props', () => {
    useReducedMotionMock.mockReturnValue(false);
    render(
      <Reveal delay={0.2} y={16}>
        Content
      </Reveal>
    );

    const wrapper = screen.getByText('Content');
    expect(wrapper.getAttribute('data-initial')).toContain('"y":16');
    expect(wrapper.getAttribute('data-transition')).toContain('"delay":0.2');
  });

  it('passes className to the wrapper', () => {
    useReducedMotionMock.mockReturnValue(false);
    render(<Reveal className="custom-class">Content</Reveal>);

    expect(screen.getByText('Content')).toHaveClass('custom-class');
  });

  it('supports custom tag mapping', () => {
    useReducedMotionMock.mockReturnValue(false);
    render(<Reveal as="article">Content</Reveal>);

    const wrapper = screen.getByText('Content');
    expect(wrapper.tagName.toLowerCase()).toBe('article');
  });
});
