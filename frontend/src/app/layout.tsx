import type { Metadata } from "next";

import NavBar from "@/components/NavBar";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Discovery Agent",
  description: "AI inventory, shadow AI and coverage across AWS, GCP and Azure",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <NavBar />
        <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}