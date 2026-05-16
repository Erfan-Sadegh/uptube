import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Uptube",
  description: "Upload Aparat videos to YouTube with generated subtitles"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
