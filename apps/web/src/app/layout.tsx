import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Praxis — Personal AI Execution Partner",
  description: "Overcome task-initiation friction and turn commitments into verified outcomes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-canvas-walnut text-cream antialiased selection:bg-ember/30 selection:text-cream font-sans">
        {children}
      </body>
    </html>
  );
}
