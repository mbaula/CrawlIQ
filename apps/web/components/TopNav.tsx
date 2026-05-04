"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "./ThemeToggle";

const links = [
  { href: "/", label: "Index" },
  { href: "/crawl", label: "Crawl" },
  { href: "/jobs", label: "Jobs" },
  { href: "/search", label: "Search" },
  { href: "/stats", label: "Stats" },
] as const;

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-paper/90 backdrop-blur-sm transition-colors duration-200">
      <div className="mx-auto flex h-12 max-w-content items-center justify-between gap-4 px-5 sm:px-8">
        <div className="flex min-w-0 items-center gap-6">
          <Link
            href="/"
            className="font-serif text-lg font-semibold tracking-tight text-ink transition-colors duration-150 hover:text-accent"
          >
            CrawlIQ
          </Link>
          <nav className="hidden min-w-0 sm:flex sm:items-center sm:gap-1" aria-label="Primary">
            {links.map(({ href, label }) => {
              const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    "rounded px-2 py-1 font-mono text-[11px] uppercase tracking-widest transition-colors duration-150",
                    active
                      ? "bg-rule/40 text-ink"
                      : "text-muted hover:bg-rule/25 hover:text-ink",
                  ].join(" ")}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
        <ThemeToggle />
      </div>
      <nav className="flex border-t border-rule/60 px-3 py-2 sm:hidden" aria-label="Primary mobile">
        <div className="flex w-full flex-wrap gap-1">
          {links.map(({ href, label }) => {
            const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={[
                  "rounded px-2 py-1 font-mono text-[10px] uppercase tracking-widest transition-colors duration-150",
                  active ? "bg-rule/40 text-ink" : "text-muted hover:bg-rule/25 hover:text-ink",
                ].join(" ")}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
