import { render } from '@testing-library/react';
import { InstructorProfileSkeleton } from '../InstructorProfileSkeleton';

describe('InstructorProfileSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = render(<InstructorProfileSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('renders mobile header skeleton', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Mobile header is hidden on large screens
    const mobileHeader = container.querySelector('.lg\\:hidden.sticky');
    expect(mobileHeader).toBeInTheDocument();
  });

  it('renders desktop header skeleton', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Desktop header is hidden on small screens
    const desktopHeader = container.querySelector('.hidden.lg\\:block.border-b');
    expect(desktopHeader).toBeInTheDocument();
  });

  it('renders profile avatar skeleton', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Look for rounded-full skeleton (avatar)
    const avatarSkeleton = container.querySelector('.rounded-full');
    expect(avatarSkeleton).toBeInTheDocument();
  });

  it('renders grid layout for content', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Main grid with 3 columns on large screens
    const grid = container.querySelector('.grid.gap-8.lg\\:grid-cols-3');
    expect(grid).toBeInTheDocument();
  });

  it('renders left column with main content', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Left column spans 2 columns
    const leftColumn = container.querySelector('.lg\\:col-span-2');
    expect(leftColumn).toBeInTheDocument();
  });

  it('renders services section skeleton with cards', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Services section has cards in a grid
    const serviceCards = container.querySelectorAll('.grid.gap-4.md\\:grid-cols-2 > *');
    expect(serviceCards.length).toBe(2); // Two service card skeletons
  });

  it('renders mobile availability section', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Mobile availability is visible only on small screens
    const mobileAvailability = container.querySelector('.lg\\:hidden .space-y-3');
    expect(mobileAvailability).toBeInTheDocument();
  });

  it('renders desktop availability section', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Desktop availability is hidden on small screens
    const desktopAvailability = container.querySelector('.hidden.lg\\:block .space-y-3');
    expect(desktopAvailability).toBeInTheDocument();
  });

  it('renders availability day skeletons', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Should have multiple day rows in availability section
    // Each availability section has 5 day skeletons
    const daySections = container.querySelectorAll('.space-y-3 > .flex');
    expect(daySections.length).toBeGreaterThanOrEqual(5);
  });

  it('renders reviews section skeleton', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Reviews section has multiple review card skeletons
    const reviewCards = container.querySelectorAll('.space-y-4 > [class*="card"]');
    expect(reviewCards.length).toBeGreaterThanOrEqual(2);
  });

  it('renders sticky booking button skeleton for mobile', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Mobile booking button is fixed at bottom
    const mobileBooking = container.querySelector('.fixed.bottom-0.left-0.right-0.lg\\:hidden');
    expect(mobileBooking).toBeInTheDocument();
  });

  it('renders info cards in right column', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Right column has info card skeletons
    const infoCards = container.querySelectorAll('.space-y-6 > [class*="card"]');
    expect(infoCards.length).toBeGreaterThanOrEqual(2);
  });

  it('has proper min-height for full page', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass('min-h-screen');
  });

  it('uses Skeleton components for placeholders', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Skeleton components render with height/width Tailwind classes
    // Count elements with height classes (h-*) that represent skeleton placeholders
    const heightElements = container.querySelectorAll('[class*="h-"]');
    // Filter to only count elements that have both h-* and w-* (typical skeleton pattern)
    const skeletonLikeElements = Array.from(heightElements).filter((el) =>
      el.className.includes('w-')
    );
    expect(skeletonLikeElements.length).toBeGreaterThan(10);
  });

  it('renders with responsive design classes', () => {
    const { container } = render(<InstructorProfileSkeleton />);

    // Check for responsive classes
    expect(container.querySelector('.lg\\:hidden')).toBeInTheDocument();
    expect(container.querySelector('.hidden.lg\\:block')).toBeInTheDocument();
    expect(container.querySelector('.md\\:grid-cols-2')).toBeInTheDocument();
  });
});
