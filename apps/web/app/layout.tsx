import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata={title:"CareBridge AI | Personal health record",description:"A Bangla-first personal space to organize health records."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
