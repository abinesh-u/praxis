import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Praxis",
  description: "Personal AI execution partner",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, -apple-system, sans-serif", margin: 0, padding: "2rem" }}>
        {children}
      </body>
    </html>
  );
}
