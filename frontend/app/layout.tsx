import type { Metadata } from "next";
import { Alegreya_Sans, Azeret_Mono, Newsreader } from "next/font/google";
import "./globals.css";

export const metadata: Metadata = {
  title: "Field Briefing — Community Health AI",
  description:
    "Supervisor workspace for community health worker oversight. Built on OpenMRS FHIR data.",
};

// Self-host the three families via next/font. This inlines the @font-face
// rules so the browser never falls back to a system font for the weights
// we actually use — that fallback is what made small sidebar labels look
// pixelated/faux-bold before this change.
const sans = Alegreya_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

const mono = Azeret_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${serif.variable} ${mono.variable}`}
    >
      <body className="antialiased">{children}</body>
    </html>
  );
}
