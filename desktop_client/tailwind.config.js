/** @type {import('tailwindcss').Config} */
// Hightower Systems palette, lifted from sentry-wms/mobile/src/theme/styles.js
// so the cashier register reads as the same product line as the warehouse
// handheld. Light surfaces, cream-tinted cards, brand red for primary
// actions, copper for accents, mono everywhere for SKUs and labels.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#8e2716",
          copper: "#b87333",
          cream: "#fdf4e3",
        },
        surface: {
          DEFAULT: "#ffffff",
          card: "#f7f3ec",
          border: "#e0d9cc",
          input: "#f7f3ec",
          inputBorder: "#d6cfc0",
        },
        ink: {
          DEFAULT: "#1a1a1a",
          muted: "#7a7060",
          soft: "#999080",
          placeholder: "#b0a898",
        },
        status: {
          success: "#34a853",
          warning: "#b87333",
          danger: "#8e2716",
        },
        warehouse: {
          store: "#5b9bd5",
          afc: "#c47a3a",
          web: "#9c87c1",
        },
      },
      fontFamily: {
        mono: ["Menlo", "ui-monospace", "SFMono-Regular", "monospace"],
        sans: [
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "12px",
        badge: "6px",
      },
    },
  },
  plugins: [],
};
