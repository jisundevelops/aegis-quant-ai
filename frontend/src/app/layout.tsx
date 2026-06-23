/**
 * Root layout for Aegis Quant AI frontend.
 * Phase 8 implements the full layout (header, nav, sidebar).
 */
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aegis Quant AI",
  description: "Modular, institutional-grade AI trading research assistant.",
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
