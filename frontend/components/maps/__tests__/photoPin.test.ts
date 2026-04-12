import {
  createClusterPinIcon,
  createInstructorPhotoPinIcon,
  escapeAttribute,
  escapeHtml,
} from '../photoPin';

jest.mock('leaflet', () => {
  const divIcon = jest.fn((options: Record<string, unknown>) => ({ options }));
  return {
    __esModule: true,
    default: { divIcon },
    divIcon,
  };
});

describe('photoPin', () => {
  it('returns a valid Leaflet divIcon for instructor photo pins', () => {
    const icon = createInstructorPhotoPinIcon({
      displayName: 'Ava L.',
      profilePictureUrl: 'https://cdn.example.com/ava.jpg',
    }) as { options?: { html?: string; className?: string } };

    expect(icon.options?.className).toBe('instructor-photo-pin-icon');
    expect(icon.options?.html).toContain('data-photo-pin="true"');
    expect(icon.options?.html).toContain('src="https://cdn.example.com/ava.jpg"');
    expect(icon.options?.html).toContain('background:#F3E8FF;clip-path:polygon(50% 100%,0 0,100% 0);');
  });

  it('escapes untrusted text and attribute values before injecting HTML', () => {
    expect(escapeHtml(`Ava <script>alert("x")</script>`)).toBe(
      'Ava &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
    );
    expect(escapeAttribute(`https://cdn.example.com/avatar.jpg?x="1"&y=<bad>`)).toBe(
      'https://cdn.example.com/avatar.jpg?x=&quot;1&quot;&amp;y=&lt;bad&gt;'
    );

    const icon = createInstructorPhotoPinIcon({
      displayName: `Ava <script>alert("x")</script>`,
      profilePictureUrl: `https://cdn.example.com/avatar.jpg?x="1"&y=<bad>`,
    }) as { options?: { html?: string } };
    const html = icon.options?.html ?? '';

    expect(html).not.toContain('<script>');
    expect(html).toContain('Ava &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
    expect(html).toContain(
      'src="https://cdn.example.com/avatar.jpg?x=&quot;1&quot;&amp;y=&lt;bad&gt;"'
    );
  });

  it('renders the lavender person-icon fallback pin when no photo is provided', () => {
    const icon = createInstructorPhotoPinIcon({
      displayName: 'Fallback Pin',
      profilePictureUrl: null,
      state: 'hovered',
    }) as { options?: { html?: string } };
    const html = icon.options?.html ?? '';

    expect(html).toContain('data-photo-fallback="true"');
    expect(html).toContain('#F3E8FF');
    expect(html).toContain('circle cx="12" cy="8" r="4"');
    expect(html).toContain('data-pin-state="hovered"');
    expect(html).not.toContain('<img');
  });

  it('renders the branded cluster icon HTML with the count in the bubble', () => {
    const icon = createClusterPinIcon(4) as { options?: { html?: string; className?: string } };

    expect(icon.options?.className).toBe('instructor-photo-pin-cluster-icon');
    expect(icon.options?.html).toContain('data-cluster-pin="true"');
    expect(icon.options?.html).toContain('data-cluster-count="4"');
    expect(icon.options?.html).toContain('role="img"');
    expect(icon.options?.html).toContain('aria-label="4 instructors in this area"');
    expect(icon.options?.html).toContain('#7E22CE');
  });
});
