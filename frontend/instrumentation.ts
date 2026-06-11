
import { registerOTel } from "@vercel/otel";

export function register() {
  registerOTel({
    serviceName: "pixel_dream_agent-frontend",
  });
}
