import forms from "@tailwindcss/forms";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        slate: {
          950: "#08111a",
        },
        brand: {
          50: "#eefbfd",
          100: "#d6f2f8",
          200: "#afdfeb",
          300: "#73c4d7",
          400: "#35a3bf",
          500: "#1886a6",
          600: "#126b86",
          700: "#12566b",
          800: "#154758",
          900: "#173c4a",
        },
        ember: {
          100: "#fff1eb",
          200: "#ffd1bf",
          300: "#ffa37e",
          400: "#ff7d51",
          500: "#f35f2d",
        },
      },
      boxShadow: {
        glow: "0 30px 90px rgba(6, 17, 26, 0.20)",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [forms],
};
