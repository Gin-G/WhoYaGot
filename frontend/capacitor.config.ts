import type { CapacitorConfig } from '@capacitor/cli'

// Baked into android/app/src/main/assets/capacitor.config.json by `cap sync`,
// so this is read at build time, not on the device. Same variable the web
// build compiles in, because Android signs in against the *web* client: Google
// stamps that ID into the token's aud, which is what the API checks.
//
// Left out entirely when unset. The plugin would otherwise fall back to its own
// placeholder string resource and fail at sign-in with nothing useful to say.
const googleClientId = process.env.VITE_GOOGLE_CLIENT_ID?.trim()

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
    ...(googleClientId
      ? {
          GoogleAuth: {
            clientId: googleClientId,
            scopes: ['profile', 'email'],
            forceCodeForRefreshToken: false,
          },
        }
      : {}),
  },
}

export default config
