import type { NextRequest } from "next/server";

export function shouldUseSecureCookies(request: NextRequest): boolean {
  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto) {
    return forwardedProto.includes("https");
  }

  return request.nextUrl.protocol === "https:";
}
