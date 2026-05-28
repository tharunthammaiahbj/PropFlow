import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PropFlow — AI Intake for Property & Design",
  description:
    "Omnichannel AI consultant for property and design services. Collects client requirements over WhatsApp and voice calls, then forwards structured leads to your team.",
  openGraph: {
    title: "PropFlow — AI Intake for Property & Design",
    description: "Try the live AI demo — talk to Sophia, your interior design consultant.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
