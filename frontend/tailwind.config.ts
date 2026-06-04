import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#06070b", 900: "#0a0c12", 800: "#11141d", 700: "#171b27" },
        glass: "rgba(255,255,255,0.035)",
        long: { DEFAULT: "#10b981", soft: "#34d399" },
        short: { DEFAULT: "#f43f5e", soft: "#fb7185" },
        accent: { DEFAULT: "#22d3ee", soft: "#67e8f9", deep: "#6366f1" },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34,211,238,0.15), 0 0 24px -4px rgba(34,211,238,0.35)",
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 20px 50px -20px rgba(0,0,0,0.8)",
      },
      keyframes: {
        pulseGlow: {
          "0%,100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        sweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(100%)" } },
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
      },
      animation: {
        pulseGlow: "pulseGlow 2.4s ease-in-out infinite",
        sweep: "sweep 2.2s linear infinite",
        marquee: "marquee 45s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
