/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        horology: {
          bg: "#090d16",
          card: "#111827",
          border: "#1f2937",
          gold: "#d4af37",
          amber: "#f59e0b",
        },
      },
    },
  },
  plugins: [],
}
