/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Rewrite proxy: forwards /api/* from the Next.js server to the backend.
  // This avoids CORS issues — the browser only sees same-origin requests.
  // NEXT_PUBLIC_API_URL must be set on Vercel (e.g. https://your-app.onrender.com)
  async rewrites() {
    const backendUrl =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
