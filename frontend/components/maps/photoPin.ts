import L from 'leaflet';

const BRAND_DARK = '#7E22CE';
const LAVENDER = '#F3E8FF';
const PHOTO_DIAMETER = 44;
const PIN_HEIGHT = 56;

export type PhotoPinState = 'default' | 'hovered' | 'focused';

type InstructorPhotoPinOptions = {
  displayName?: string;
  profilePictureUrl?: string | null;
  state?: PhotoPinState;
};

const getPinScale = (state: PhotoPinState): number => {
  if (state === 'focused') return 1.08;
  if (state === 'hovered') return 1.04;
  return 1;
};

const getPinShadow = (state: PhotoPinState): string => {
  if (state === 'focused') {
    return '0 0 0 5px rgba(126,34,206,0.28), 0 16px 30px rgba(126,34,206,0.22)';
  }
  if (state === 'hovered') {
    return '0 0 0 4px rgba(126,34,206,0.18), 0 12px 24px rgba(15,23,42,0.18)';
  }
  return '0 10px 22px rgba(15,23,42,0.18)';
};

const getPinZIndex = (state: PhotoPinState): number => {
  if (state === 'focused') return 32;
  if (state === 'hovered') return 24;
  return 12;
};

export function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function escapeAttribute(value: string): string {
  return escapeHtml(value);
}

function buildPersonIconSvg(color: string = BRAND_DARK): string {
  return [
    `<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" `,
    `xmlns="http://www.w3.org/2000/svg">`,
    `<path d="M20 21C20 17.6863 16.4183 15 12 15C7.58172 15 4 17.6863 4 21" `,
    `stroke="${color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    `<circle cx="12" cy="8" r="4" stroke="${color}" stroke-width="2.1"/>`,
    `</svg>`,
  ].join('');
}

function buildPinTail(fill: string): string {
  return [
    `<div aria-hidden="true" style="position:absolute;left:50%;top:31px;width:20px;height:20px;transform:translateX(-50%);">`,
    `<div style="position:absolute;inset:0;background:#FFFFFF;clip-path:polygon(50% 100%,0 0,100% 0);"></div>`,
    `<div style="position:absolute;left:50%;top:3px;width:14px;height:14px;transform:translateX(-50%);background:${fill};clip-path:polygon(50% 100%,0 0,100% 0);"></div>`,
    `</div>`,
  ].join('');
}

export function createInstructorPhotoPinIcon({
  displayName,
  profilePictureUrl,
  state = 'default',
}: InstructorPhotoPinOptions): L.DivIcon {
  const safeDisplayName = escapeAttribute((displayName || 'Instructor').trim() || 'Instructor');
  const safePhotoUrl =
    typeof profilePictureUrl === 'string' && profilePictureUrl.trim().length > 0
      ? escapeAttribute(profilePictureUrl.trim())
      : '';
  const scale = getPinScale(state);
  const shadow = getPinShadow(state);
  const zIndex = getPinZIndex(state);

  const html = [
    `<div data-photo-pin="true" data-pin-state="${state}" role="img" aria-label="${safeDisplayName} location pin" `,
    `style="position:relative;width:${PHOTO_DIAMETER}px;height:${PIN_HEIGHT}px;display:flex;align-items:flex-start;justify-content:center;pointer-events:auto;z-index:${zIndex};">`,
    buildPinTail(LAVENDER),
    `<div class="instructor-photo-pin__bubble" style="position:relative;width:${PHOTO_DIAMETER}px;height:${PHOTO_DIAMETER}px;border-radius:999px;border:3px solid #FFFFFF;overflow:hidden;background:${LAVENDER};box-shadow:${shadow};transform:scale(${scale});transform-origin:center bottom;transition:transform 180ms ease, box-shadow 180ms ease;">`,
    `<div class="instructor-photo-pin__fallback" data-photo-fallback="true" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:${LAVENDER};">`,
    buildPersonIconSvg(),
    `</div>`,
    safePhotoUrl
      ? `<img src="${safePhotoUrl}" alt="${safeDisplayName}" loading="lazy" referrerpolicy="no-referrer" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:999px;background:${LAVENDER};" onerror="this.style.display='none';this.setAttribute('data-photo-error','true');" />`
      : '',
    `</div>`,
    `</div>`,
  ].join('');

  return L.divIcon({
    html,
    className: 'instructor-photo-pin-icon',
    iconSize: [PHOTO_DIAMETER, PIN_HEIGHT],
    iconAnchor: [PHOTO_DIAMETER / 2, PIN_HEIGHT],
    popupAnchor: [0, -PHOTO_DIAMETER + 6],
  });
}

export function createClusterPinIcon(count: number): L.DivIcon {
  const safeCount = Number.isFinite(count) ? Math.max(1, Math.round(count)) : 1;
  const html = [
    `<div data-cluster-pin="true" data-cluster-count="${safeCount}" role="img" aria-label="${safeCount} instructors in this area" style="width:${PHOTO_DIAMETER}px;height:${PHOTO_DIAMETER}px;border-radius:999px;background:${LAVENDER};border:3px solid #FFFFFF;display:flex;align-items:center;justify-content:center;box-shadow:0 12px 24px rgba(126,34,206,0.16);font-size:16px;font-weight:800;line-height:1;color:${BRAND_DARK};">`,
    `${safeCount}`,
    `</div>`,
  ].join('');

  return L.divIcon({
    html,
    className: 'instructor-photo-pin-cluster-icon',
    iconSize: [PHOTO_DIAMETER, PHOTO_DIAMETER],
    iconAnchor: [PHOTO_DIAMETER / 2, PHOTO_DIAMETER / 2],
  });
}
