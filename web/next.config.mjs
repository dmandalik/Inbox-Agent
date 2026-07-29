/** @type {import('next').NextConfig} */
const API = process.env.INBOX_API_BASE || "http://127.0.0.1:8000";

const nextConfig = {
  // Proxy /api/* to the FastAPI backend so the browser calls same-origin.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
