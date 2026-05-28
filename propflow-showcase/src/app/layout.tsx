import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PropFlow — AI Intake Platform",
  description:
    "Omnichannel AI consultant for property and design services. Collects client requirements over WhatsApp and voice calls, then delivers structured briefs to your team automatically.",
  openGraph: {
    title: "PropFlow — AI Intake Platform",
    description: "Try the live AI demo — talk to Sophia, your interior design consultant.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
