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
        <div className="bg-amber-100 px-6 py-1.5 text-center text-xs text-amber-900">
          Demo data: AWS simulated with moto, GCP and Azure from fixtures. No live cloud accounts.
        </div>
        <NavBar />
        <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}