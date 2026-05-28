import type { Metadata } from "next";
import { Fraunces, Roboto } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  style: ["normal", "italic"],
});

const roboto = Roboto({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["300", "400", "500", "700"],
});

export const metadata: Metadata = {
  title: "PropFlow — AI Intake Platform",
  description:
    "Omnichannel AI consultant for property and design services. Collects client requirements over WhatsApp and voice calls, then delivers structured briefs to your team automatically.",
  openGraph: {
    title: "PropFlow — AI Intake Platform",
    description: "Try the live AI demo — talk to Jessica, PropFlow's AI consultant.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${fraunces.variable} ${roboto.variable}`}>
      <body>{children}</body>
    </html>
  );
}
