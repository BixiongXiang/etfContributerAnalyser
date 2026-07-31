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
        // Contribution colour scale
        gain: {
          light: "#dcfce7",
          DEFAULT: "#16a34a",
          dark: "#14532d",
        },
        loss: {
          light: "#fee2e2",
          DEFAULT: "#dc2626",
          dark: "#7f1d1d",
        },
        neutral: {
          bar: "#e5e7eb",
        },
      },
    },
  },
  plugins: [],
};

export default config;
