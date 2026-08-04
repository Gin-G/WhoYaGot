/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // The concourse: stadium concrete and signage.
        concrete: {
          DEFAULT: '#C9C5BD',
          light: '#DEDBD4',
          dark: '#A9A49B',
        },
        ink: {
          DEFAULT: '#14171A',
          soft: '#3A4046',
        },
        chalk: '#F5F3EF',
        // Reserved for state only — never decoration.
        signal: '#FF4B12',
      },
      fontFamily: {
        // One family doing three jobs via its width axis.
        sans: ['Archivo Variable', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'name-sm': ['clamp(1.5rem, 5vw, 2.75rem)', { lineHeight: '0.88', letterSpacing: '-0.02em' }],
        'name-lg': ['clamp(2.5rem, 9vw, 6rem)', { lineHeight: '0.84', letterSpacing: '-0.03em' }],
      },
      transitionTimingFunction: {
        slam: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
