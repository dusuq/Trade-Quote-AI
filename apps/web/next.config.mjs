/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The gateway base URL is read at runtime by the API client (src/config.ts);
  // exposed to the browser via NEXT_PUBLIC_API_URL.
};

export default nextConfig;
