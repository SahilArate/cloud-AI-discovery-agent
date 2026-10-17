"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Inventory" },
  { href: "/review", label: "Review queue" },
  { href: "/coverage", label: "Coverage" },
  { href: "/changes", label: "Changes" },
  { href: "/costs", label: "LLM cost" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="border-b border-gray-200 dark:border-gray-800">
      <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-3">
        <span className="font-semibold">AI Discovery Agent</span>
        <nav className="flex gap-1">
          {LINKS.map((link) => {
            const isActive = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded px-3 py-1.5 text-sm ${
                  isActive
                    ? "bg-gray-100 font-medium dark:bg-gray-800"
                    : "text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-900"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}