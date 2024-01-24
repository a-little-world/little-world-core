import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.littleworld',
  appName: 'littleworld',
  webDir: 'build',
  server: {
    androidScheme: 'https',
    hostname: '__BACKEND_URL__',
    allowNavigation: []
  },
  plugins: {
    CapacitorHttp: {
      enabled: true,
    },
    CapacitorCookies: {
      enabled: true
    }
  },
  android: {
    allowMixedContent: true
  },
  bundledWebRuntime: false,
};

export default config;