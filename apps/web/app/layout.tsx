import type { Metadata } from "next";
import { Fragment, type ReactNode } from "react";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";

import { TopNav } from "@/components/TopNav";
import { getApiBaseUrl } from "@/lib/api";

import { Providers } from "./providers";
import "./globals.css";

const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

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
    <html lang="en" suppressHydrationWarning className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body className="font-sans">
        <Providers>
          <Fragment>
            <TopNav />
            <div className="mx-auto max-w-content px-5 pb-16 pt-8 sm:px-8 sm:pt-10">{children}</div>
            <footer className="mx-auto max-w-content border-t border-rule px-5 py-6 sm:px-8">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted">
                API base <span className="text-ink">{apiBase}</span>
              </p>
            </footer>
          </Fragment>
        </Providers>
      </body>
    </html>
  );
}
