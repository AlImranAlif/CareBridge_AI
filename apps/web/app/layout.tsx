import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import { getApiStatus } from "@/lib/api";
import "./globals.css";

export const metadata: Metadata = {
  title: "CareBridge AI | Your health, organized",
  description: "A calm, personal space to organize your health records.",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const apiStatus = await getApiStatus();
  return <html lang="en"><body><div className="min-h-screen lg:flex"><Sidebar apiStatus={apiStatus}/>{children}</div></body></html>;
}
