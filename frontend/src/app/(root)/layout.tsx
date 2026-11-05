import type { ReactNode } from "react";

import { fontVariables } from "@/lib/fonts";

import "../globals.css";

type RootRedirectLayoutProps = {
  children: ReactNode;
};

export default function RootRedirectLayout({ children }: RootRedirectLayoutProps) {
  return (
    <html lang="bn">
      <body className={fontVariables}>{children}</body>
    </html>
  );
}
