import type { Metadata } from "next";
import { Roboto } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import { AuthProviders } from "@/context/AuthProviders";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import Sidebar from "@/components/Sidebar";
import "../globals.css";

const roboto = Roboto({
  weight: ["300", "400", "500", "700"],
  style: ["normal"],
  subsets: ["latin"],
  display: "swap",
  variable: "--font-roboto",
});

export const metadata: Metadata = {
  title: "Master Data UI",
  description: "OpenG2P Master Data UI",
};

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body className={`${roboto.variable} ${roboto.className} antialiased`}>
        <NextIntlClientProvider messages={messages}>
          <AuthProviders>
            <div className="flex h-dvh flex-col overflow-hidden bg-[#F3F1F4]">
              <Header />
              <div className="flex min-h-0 flex-1 overflow-hidden">
                <Sidebar />
                <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                  {children}
                </main>
              </div>
              <Footer />
            </div>
          </AuthProviders>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
