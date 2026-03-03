import type { Config } from "tailwindcss";

export default {
    darkMode: ["class"],
    content: [
        "./pages/**/*.{ts,tsx}",
        "./components/**/*.{ts,tsx}",
        "./app/**/*.{ts,tsx}",
        "./src/**/*.{ts,tsx}",
    ],
    prefix: "",
    theme: {
        container: {
            center: true,
            padding: "2rem",
            screens: {
                "2xl": "1400px",
            },
        },
        extend: {
            colors: {
                /* Indian-inspired palette */
                cream: "#f8f6f1",
                indigo: {
                    DEFAULT: "#1e3a8a",
                    light: "#2d4ea1",
                    dark: "#152c6b",
                },
                saffron: {
                    DEFAULT: "#f59e0b",
                    light: "#fbbf24",
                    dark: "#d97706",
                },
                teal: {
                    DEFAULT: "#0d9488",
                    light: "#14b8a6",
                    dark: "#0f766e",
                },
                vermillion: {
                    DEFAULT: "#dc2626",
                    light: "#ef4444",
                    dark: "#b91c1c",
                },

                /* Shadcn compat */
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                primary: {
                    DEFAULT: "hsl(var(--primary))",
                    foreground: "hsl(var(--primary-foreground))",
                },
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "hsl(var(--accent))",
                    foreground: "hsl(var(--accent-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 4px)",
            },
            fontFamily: {
                heading: ['"Playfair Display"', 'serif'],
                body: ['"DM Sans"', 'system-ui', 'sans-serif'],
                script: ['"Noto Sans Devanagari"', '"Noto Sans Bengali"', '"Noto Sans Tamil"', '"Noto Sans Telugu"', '"Noto Sans Kannada"', '"Noto Sans Malayalam"', '"Noto Sans Gurmukhi"', '"Noto Sans Gujarati"', 'sans-serif'],
            },
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
                "fade-in": {
                    "0%": { opacity: "0", transform: "translateY(12px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
                "slide-up": {
                    "0%": { opacity: "0", transform: "translateY(24px)" },
                    "100%": { opacity: "1", transform: "translateY(0)" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
                "fade-in": "fade-in 0.5s ease-out forwards",
                "slide-up": "slide-up 0.6s ease-out forwards",
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
} satisfies Config;
