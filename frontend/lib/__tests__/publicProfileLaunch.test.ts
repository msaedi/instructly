import { getPublicProfileLaunchState } from '../publicProfileLaunch';

describe('getPublicProfileLaunchState', () => {
  it('keeps the public profile button disabled before student launch', () => {
    expect(getPublicProfileLaunchState(false)).toEqual({
      isEnabled: false,
      title: 'Available after student launch',
    });
  });

  it('enables the public profile button after student launch', () => {
    expect(getPublicProfileLaunchState(true)).toEqual({
      isEnabled: true,
      title: 'View your public instructor page',
    });
  });
});
