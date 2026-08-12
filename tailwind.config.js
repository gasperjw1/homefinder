/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#080d1a',
          900: '#0a0f1a',
          800: '#0f172a',
          700: '#141c2e',
          600: '#1a2540',
        },
      },
    },
  },
  plugins: [],
}
