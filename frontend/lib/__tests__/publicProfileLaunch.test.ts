import { getPublicProfileLaunchState } from '../publicProfileLaunch';

describe('getPublicProfileLaunchState', () => {
  it('keeps the public profile button disabled on beta before student launch', () => {
    expect(getPublicProfileLaunchState(false, 'beta.instainstru.com')).toEqual({
      isEnabled: false,
      title: 'Available after student launch',
    });
  });

  it('enables the public profile button on beta after student launch', () => {
    expect(getPublicProfileLaunchState(true, 'beta-local.instainstru.com')).toEqual({
      isEnabled: true,
      title: 'View your public instructor page',
    });
  });

  it('always enables the public profile button on preview hosts', () => {
    expect(getPublicProfileLaunchState(false, 'preview.instainstru.com')).toEqual({
      isEnabled: true,
      title: 'View your public instructor page',
    });
  });

  it('always enables the public profile button on localhost', () => {
    expect(getPublicProfileLaunchState(false, 'localhost:3000')).toEqual({
      isEnabled: true,
      title: 'View your public instructor page',
    });
  });

  it('always enables the public profile button on non-beta hosts', () => {
    expect(getPublicProfileLaunchState(false, 'app.instainstru.com')).toEqual({
      isEnabled: true,
      title: 'View your public instructor page',
    });
  });
});
