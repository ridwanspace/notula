import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "sonner";
import { Shell } from "@/components/shell";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Notula",
  description:
    "Meeting minutes from audio: diarized transcript as the system of record, re-runnable structured summaries, measured per-stage cost.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased`}>
        <Shell>{children}</Shell>
        <Toaster position="bottom-right" />
      </body>
    </html>
  );
}
