import type { FastifyInstance } from "fastify";
import { config } from "../config.js";

export default async function healthRoutes(app: FastifyInstance): Promise<void> {
  app.get("/health", async () => ({
    status: "ok",
    service: "api-gateway",
    env: config.nodeEnv,
  }));
}
