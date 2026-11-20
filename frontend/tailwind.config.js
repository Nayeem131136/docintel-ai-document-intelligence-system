/** Colours are centralised here: change `brand` / `accent` to re-theme the whole app. */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"] },
      colors: {
        brand: {
          50: "#f3f4fa", 100: "#e4e6f4", 200: "#c9cde8", 300: "#9fa6d3", 400: "#6f78b7",
          500: "#4a5398", 600: "#363e7a", 700: "#2a3061", 800: "#20254b", 900: "#1a1a2e", 950: "#101021",
        },
        accent: { 50: "#ecfdf8", 100: "#d1faee", 400: "#2dd4b4", 500: "#14b89c", 600: "#0f9783", 700: "#0f7869" },
      },
      keyframes: {
        shimmer: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
        "fade-up": { "0%": { opacity: 0, transform: "translateY(10px)" }, "100%": { opacity: 1, transform: "none" } },
        gradient: { "0%,100%": { backgroundPosition: "0% 50%" }, "50%": { backgroundPosition: "100% 50%" } },
        beam: { "100%": { offsetDistance: "100%" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        "pulse-ring": { "0%": { boxShadow: "0 0 0 0 rgba(20,184,156,.45)" }, "100%": { boxShadow: "0 0 0 12px rgba(20,184,156,0)" } },
      },
      animation: {
        shimmer: "shimmer 2.4s linear infinite",
        "fade-up": "fade-up .45s ease-out both",
        gradient: "gradient 6s ease infinite",
        beam: "beam 6s linear infinite",
        float: "float 4s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.6s ease-out infinite",
      },
    },
  },
  plugins: [],
};
