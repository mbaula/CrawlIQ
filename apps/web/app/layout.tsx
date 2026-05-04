import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CrawlIQ",
  description: "Mini search engine dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: "2rem" }}>{children}</body>
    </html>
  );
}
