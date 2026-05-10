/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // Every color is wired to a CSS variable defined in app/globals.css so
      // we can keep the original oklch tokens from the design handoff and
      // still get Tailwind's `bg-surface`, `text-ink`, `border-line` etc.
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        line: "var(--line)",
        "line-2": "var(--line-2)",
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        "ink-3": "var(--ink-3)",
        "ink-4": "var(--ink-4)",
        accent: "var(--accent)",
        "accent-2": "var(--accent-2)",
        "accent-ink": "var(--accent-ink)",
        ok: "var(--ok)",
        "ok-bg": "var(--ok-bg)",
        warn: "var(--warn)",
        "warn-bg": "var(--warn-bg)",
        alert: "var(--alert)",
        "alert-bg": "var(--alert-bg)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
      },
      boxShadow: {
        suggest: "0 4px 12px oklch(0 0 0 / 0.04)",
        composer:
          "0 6px 18px oklch(0 0 0 / 0.04), 0 1px 2px oklch(0 0 0 / 0.04)",
        focus: "0 0 0 3px oklch(0.46 0.09 195 / 0.12)",
      },
      letterSpacing: {
        tight2: "-0.02em",
        tight1: "-0.01em",
        wide1: "0.05em",
        wide2: "0.08em",
      },
      animation: {
        spin08: "spin 0.8s linear infinite",
        pulseDot: "pulseDot 1.6s ease-out infinite",
      },
      keyframes: {
        pulseDot: {
          "0%": { boxShadow: "0 0 0 0 var(--accent)" },
          "70%": { boxShadow: "0 0 0 8px transparent" },
          "100%": { boxShadow: "0 0 0 0 transparent" },
        },
      },
    },
  },
  plugins: [],
};
