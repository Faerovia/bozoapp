import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "BOZOapp",
  description: "BOZP a PO management platforma",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="cs">
      <body>{children}</body>
    </html>
  );
}
