import type { NextConfig } from "next";

const backendBaseUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const slackRedirectUrl = process.env.SLACK_REDIRECT_URI ?? "";

function toHostname(url: string) {
  try {
    return new URL(url).hostname;
  } catch {
    return undefined;
  }
}

const allowedDevOrigins = Array.from(
  new Set(
    [
      "localhost",
      "127.0.0.1",
      toHostname(slackRedirectUrl),
    ].filter((value): value is string => Boolean(value)),
  ),
);

const nextConfig: NextConfig = {
  allowedDevOrigins,
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${backendBaseUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
