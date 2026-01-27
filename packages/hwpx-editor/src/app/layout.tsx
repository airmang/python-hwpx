import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HWPX Editor",
  description: "HWPX 문서 편집기",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
