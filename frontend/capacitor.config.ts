import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'net.nickknows.whoyagot',
  appName: 'Who Ya Got',
  webDir: 'dist',
  android: {
    // The webview origin the API must allow in CORS.
    // Anything else and every request fails as a cross-origin error.
    allowMixedContent: false,
  },
  server: {
    androidScheme: 'https',
  },
  plugins: {
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#C9C5BD',
    },
  },
}

export default config
