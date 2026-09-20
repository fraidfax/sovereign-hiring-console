import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#05070d",
          900: "#0a0f1a",
          800: "#0f1626",
          700: "#161f35",
          600: "#202c48",
        },
        accent: {
          DEFAULT: "#4fd1c5",
          dim: "#2a9d93",
          bright: "#7ee8dc",
        },
        warn: {
          DEFAULT: "#f0a94e",
          dim: "#8a5a1e",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
