import { z } from "zod";

const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url(),
});

const parsedEnv = envSchema.safeParse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
});

if (!parsedEnv.success) {
  throw new Error(
    "Invalid environment configuration: NEXT_PUBLIC_API_BASE_URL is missing or invalid."
  );
}

export const env = {
  apiBaseUrl: parsedEnv.data.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/, ""),
};
