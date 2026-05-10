/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The browser talks to the backend directly; no rewrites needed because
  // the backend allow-lists localhost:3000 via FastAPI CORS middleware.
  // NEXT_PUBLIC_BACKEND_URL is read by lib/api.ts.
};

export default nextConfig;
