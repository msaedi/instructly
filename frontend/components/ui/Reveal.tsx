'use client';

import { MotionProps, m, useReducedMotion } from 'motion/react';
import React, { PropsWithChildren, ElementType } from 'react';

type RevealProps = PropsWithChildren<{
  as?: keyof React.JSX.IntrinsicElements;
  delay?: number;
  y?: number;
  className?: string;
}> & MotionProps;

export default function Reveal({ as: Tag = 'div', delay = 0.05, y = 8, className, children, ...rest }: RevealProps) {
  const prefersReduced = useReducedMotion();
  if (prefersReduced) {
    // Render without motion when user prefers reduced motion
    const StaticTag = Tag as ElementType;
    return <StaticTag className={className}>{children}</StaticTag>;
  }
  // Map limited set of safe intrinsic tags to motion components; default to div
  const motionMap = { div: m.div, section: m.section, article: m.article, span: m.span } as const;
  const MotionTag = motionMap[Tag as keyof typeof motionMap] || m.div;
  return (
    <MotionTag
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut', delay }}
      className={className}
      {...rest}
    >
      {children}
    </MotionTag>
  );
}
