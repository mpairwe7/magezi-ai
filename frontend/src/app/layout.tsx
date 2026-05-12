import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import Providers from '../components/Providers';
import ServiceWorkerRegistrar from '../components/ServiceWorkerRegistrar';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL || 'https://magezi-ai.renu-01.cranecloud.io'),
  title: 'Magezi — A-Level STEM Tutor',
  description:
    'Wisdom in your language. AI-powered A-Level STEM tutor for Ugandan students, aligned to the NCDC 2025 Competence-Based Curriculum.',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Magezi',
  },
  icons: {
    icon: '/favicon.svg',
    apple: '/icon-192.png',
  },
  openGraph: {
    title: 'Magezi — A-Level STEM Tutor for Uganda',
    description:
      'AI-powered Physics, Chemistry, Biology & Mathematics tutoring aligned to NCDC 2025 Competence-Based Curriculum. In English, Luganda, Swahili & Runyankole.',
    siteName: 'Magezi AI',
    locale: 'en_UG',
    type: 'website',
    url: '/',
    images: [
      { url: '/og-image.svg', width: 1200, height: 630, alt: 'Magezi — A-Level STEM Tutor for Uganda', type: 'image/svg+xml' },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Magezi — A-Level STEM Tutor',
    description: 'AI-powered STEM tutoring for Ugandan A-Level students. Physics, Chemistry, Biology & Maths — NCDC 2025 curriculum.',
    images: ['/og-image.svg'],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  themeColor: '#040a06',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <ServiceWorkerRegistrar />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
