import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sovereign Hiring Agent",
  description:
    "A transparent, human-supervised hiring agent built for data sovereignty.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-navy-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
