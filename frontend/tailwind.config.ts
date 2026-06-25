import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Aegis dark theme
        bg: {
          primary: "#0a0e14",
          secondary: "#11151c",
          tertiary: "#1a1f2a",
          card: "#141921",
        },
        border: {
          DEFAULT: "#1f242e",
          subtle: "#2a3140",
        },
        accent: {
          bull: "#00d4a0",
          bear: "#ff4757",
          neutral: "#8b95a7",
          primary: "#00d4ff",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
