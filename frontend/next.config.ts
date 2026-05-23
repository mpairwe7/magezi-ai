import type { NextConfig } from 'next';

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || 'http://localhost:8002';
const isDev = process.env.NODE_ENV !== 'production';

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,

  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${INTERNAL_API_URL}/:path*` },
    ];
  },

  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
          { key: 'Permissions-Policy', value: 'camera=(), geolocation=(), microphone=(self)' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              isDev ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: blob:",
              isDev ? "connect-src *" : "connect-src 'self'",
              "worker-src 'self'",
            ].join('; '),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
