import "./globals.css";
import React from "react";
import { AppShell } from "../components/AppShell";

export const metadata = {
  title: "CodeGuard — Autonomous Security & Code Intelligence Platform",
  description: "Enterprise Pull Request reviews powered by deterministic AST code intelligence and multi-agent verification",
  openGraph: {
    title: "CodeGuard",
    description: "Enterprise Pull Request reviews powered by deterministic AST code intelligence and multi-agent verification",
    siteName: "CodeGuard",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="bg-surface text-on-surface min-h-screen antialiased select-auto" suppressHydrationWarning>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

