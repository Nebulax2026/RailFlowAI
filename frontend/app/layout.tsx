import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RailFlowAI | Track Access Optimisation",
  description: "Validator-ready railway possession planning for NebulaX PS1."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
