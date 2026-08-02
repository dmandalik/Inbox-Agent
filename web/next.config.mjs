/** @type {import('next').NextConfig} */
const API = process.env.INBOX_API_BASE || "http://127.0.0.1:8000";

// Two build modes:
//   • dev (default): Next dev server on :3000, proxying /api/* to FastAPI.
//   • desktop (DESKTOP=1 next build): a static export in web/out that FastAPI
//     serves itself, so the whole app is one process on one origin.
const desktop = process.env.DESKTOP === "1";

const nextConfig = desktop
  ? { output: "export", images: { unoptimized: true } }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
      },
    };

export default nextConfig;
