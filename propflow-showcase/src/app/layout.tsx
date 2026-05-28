import type { Metadata } from "next";
import { Source_Serif_4, Inter, Lora } from "next/font/google";
import "./globals.css";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  style: ["normal", "italic"],
  weight: ["400", "500", "600", "700"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-reading",
  display: "swap",
  style: ["normal", "italic"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "PropFlow — AI Consultant Platform",
  description:
    "Omnichannel AI consultant for property and design services. Collects client requirements over WhatsApp and voice calls, then delivers structured briefs to your team automatically.",
  openGraph: {
    title: "PropFlow — AI Consultant Platform",
    description: "Try the live AI demo — talk to Jessica, PropFlow's AI consultant.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${sourceSerif.variable} ${inter.variable} ${lora.variable}`}>
      <body>{children}</body>
    </html>
  );
}
