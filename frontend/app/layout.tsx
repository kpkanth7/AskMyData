import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "askmydata",
  description: "Upload, connect, ask, and summarize structured data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
