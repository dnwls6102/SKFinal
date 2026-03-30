import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prototype Builder",
  description: "AI-assisted block builder for rapid web project prototyping."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
