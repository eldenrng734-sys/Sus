import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "SYNTRIX AI Sales Assistant",
    template: "%s | SYNTRIX",
  },
  description:
    "Manage leads, automate follow-ups, and improve your sales workflow with SYNTRIX AI Sales Assistant.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
