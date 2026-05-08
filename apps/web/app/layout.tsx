import type { Metadata } from "next";
import { Fragment, type ReactNode } from "react";

import { TopNav } from "@/components/TopNav";
import { getApiBaseUrl } from "@/lib/api";

import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "CrawlIQ",
    template: "%s · CrawlIQ",
  },
  description: "Bounded crawl, index, and search — lab notebook UI.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const apiBase = getApiBaseUrl();

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:wght@400;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="font-sans">
        <Providers>
          <Fragment>
            <TopNav />
            <div className="mx-auto max-w-content px-5 pb-16 pt-8 sm:px-8 sm:pt-10">{children}</div>
            <footer className="mx-auto max-w-content border-t border-rule px-5 py-6 sm:px-8">
              
            </footer>
          </Fragment>
        </Providers>
      </body>
    </html>
  );
}
