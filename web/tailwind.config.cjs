/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        glow: "0 0 0 1px rgba(34, 211, 238, 0.22), 0 16px 48px rgba(8, 47, 73, 0.24)",
      },
      colors: {
        surface: {
          950: "#040816",
          900: "#0a1021",
          800: "#10182c",
        },
      },
      keyframes: {
        "section-enter": {
          "0%": {
            opacity: "0",
            transform: "translateY(18px)",
          },
          "100%": {
            opacity: "1",
            transform: "translateY(0)",
          },
        },
      },
      animation: {
        "section-enter": "section-enter 680ms cubic-bezier(0.2, 0.8, 0.2, 1) both",
      },
    },
  },
  plugins: [],
};
