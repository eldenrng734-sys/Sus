import { z } from "zod";

const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().optional().default("/api/v1"),
});

const parsedEnv = envSchema.safeParse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});

const rawBaseUrl =
  parsedEnv.success && parsedEnv.data.NEXT_PUBLIC_API_BASE_URL
    ? parsedEnv.data.NEXT_PUBLIC_API_BASE_URL
    : "/api/v1";

export const env = {
  apiBaseUrl: rawBaseUrl.replace(/\/+$/, ""),
};
