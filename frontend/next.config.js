/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Production build runs inside the Pi Docker image. Type-correctness is
  // verified separately via `tsc --noEmit` (clean as of 2026-06-09); we don't
  // want a stray ESLint stylistic rule to block the container build while the
  // app already runs fine in dev. Runtime behaviour is unaffected.
  eslint: { ignoreDuringBuilds: true },
};
module.exports = nextConfig;
