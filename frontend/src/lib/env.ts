import { z } from "zod";

const LOCAL_API_BASE_URL = "http://localhost:8000";

const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url(),
});

const parsedEnv = envSchema.safeParse({
  NEXT_PUBLIC_API_BASE_URL:
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || LOCAL_API_BASE_URL,
});

if (!parsedEnv.success) {
  throw new Error(
    "Invalid NEXT_PUBLIC_API_BASE_URL. Set it to the backend API URL, for example http://localhost:8000.",
  );
}

export const env = {
  apiBaseUrl: parsedEnv.data.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/, ""),
};
