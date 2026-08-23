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
        // Where you sit against the crowd. Darker than `signal`, which at 11px
        // on concrete clears 2.4:1 and is unreadable; these clear AA. The arrow
        // and the number carry the meaning on their own, so colour is only ever
        // reinforcing it.
        verdict: {
          up: '#146B3F',
          down: '#B22D08',
        },
        // The field a settled row sits on. Muted into the concrete palette
        // rather than a signal green: most of a board ends up settled, and a
        // bright field repeated two hundred times reads as an alarm rather
        // than as "this part is done". Dark enough to tell from the concrete
        // at a glance, light enough to leave ink on it well past AA.
        settled: '#BCD2B4',
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
