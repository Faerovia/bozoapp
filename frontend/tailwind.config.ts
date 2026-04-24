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
        // Brand: slate-based professional palette pro B2B/admin
        brand: {
          50:  "#f0f4ff",
          100: "#e0e9ff",
          500: "#3b5bdb",
          600: "#3451c7",
          700: "#2c44b0",
        },
      },
    },
  },
  plugins: [],
};

export default config;
