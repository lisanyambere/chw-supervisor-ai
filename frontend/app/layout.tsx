import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { DebugProvider } from "@/lib/debug";

export const metadata: Metadata = {
  title: "Field Briefing — Community Health AI",
  description:
    "Supervisor workspace for community health worker oversight. Built on OpenMRS FHIR data.",
};

// Inter is the workhorse UI face — highly legible at dashboard sizes and the
// only display/body family we use now (the old serif/mono split read as
// "textbook meets terminal"). JetBrains Mono survives only for genuinely
// code-like data: tool names, ids, and tabular figures behind Debug Mode.
const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
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
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="antialiased">
        <DebugProvider>{children}</DebugProvider>
      </body>
    </html>
  );
}
