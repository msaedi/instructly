// frontend/lib/config/uiConfig.ts
export interface UIConfig {
  backgrounds: {
    blur: boolean;
    blurAmount: number;
    overlay: boolean;
    overlayOpacity: number; // 0..1
    overlayColorLight: string;
    overlayColorDark: string;
    transitionDuration: number; // ms
    enableRotation: boolean;
    rotationInterval: number; // ms
  };
  darkMode: {
    backgroundOpacity: number; // 0..1
    cardOpacity: number; // 0..1
    enableTransparency: boolean;
  };
}

export const uiConfig: UIConfig = {
  backgrounds: {
    blur: true,
    blurAmount: 12,
    overlay: true,
    overlayOpacity: 0.4,
    overlayColorLight: 'rgba(255,255,255,0.40)',
    overlayColorDark: 'rgba(0,0,0,0.60)',
    transitionDuration: 1000,
    enableRotation: true,
    rotationInterval: 0,
  },
  darkMode: {
    backgroundOpacity: 1,
    cardOpacity: 1,
    enableTransparency: false,
  },
};
