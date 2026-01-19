import { render } from '@testing-library/react';
import DynamicBackground from '../DynamicBackground';
import { getActivityBackground } from '@/lib/services/assetService';

jest.mock('@/lib/services/assetService', () => ({
  getActivityBackground: jest.fn(),
}));

const getActivityBackgroundMock = getActivityBackground as jest.Mock;

describe('DynamicBackground', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('requests a background for the activity', () => {
    getActivityBackgroundMock.mockReturnValue('/img.jpg');
    Object.defineProperty(window, 'innerWidth', { value: 1200, writable: true });

    render(<DynamicBackground activity="piano" />);

    expect(getActivityBackgroundMock).toHaveBeenCalledWith('piano', 'desktop');
  });

  it('renders with a background image when provided', () => {
    getActivityBackgroundMock.mockReturnValue('/img.jpg');
    Object.defineProperty(window, 'innerWidth', { value: 1200, writable: true });

    const { container } = render(<DynamicBackground activity="piano" />);

    const wrapper = container.firstChild as HTMLDivElement | null;
    expect(wrapper?.style.backgroundImage).toContain('/img.jpg');
  });

  it('renders without background when none returned', () => {
    getActivityBackgroundMock.mockReturnValue(null);
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });

    const { container } = render(<DynamicBackground activity="guitar" />);

    const wrapper = container.firstChild as HTMLDivElement | null;
    expect(wrapper?.style.backgroundImage).toBe('');
  });

  it('applies overlay opacity', () => {
    getActivityBackgroundMock.mockReturnValue('/img.jpg');
    Object.defineProperty(window, 'innerWidth', { value: 800, writable: true });

    const { container } = render(<DynamicBackground overlayOpacity={0.2} activity="piano" />);

    const overlay = container.querySelector('[aria-hidden="true"]') as HTMLDivElement | null;
    expect(overlay?.style.background).toMatch(/rgba\(0,\s*0,\s*0,\s*0\.2\)/);
  });

  it('passes className through', () => {
    getActivityBackgroundMock.mockReturnValue('/img.jpg');
    Object.defineProperty(window, 'innerWidth', { value: 1200, writable: true });

    const { container } = render(<DynamicBackground className="custom-class" activity="piano" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
