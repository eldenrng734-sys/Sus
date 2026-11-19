/**
 * API Error helper: maps HTTP status codes and error payloads to UI states.
 * Supports 401, 403, 404, 409, 422, and 500 error mapping (missing-parts-guide.md #16).
 */

export type ApiErrorDetails = {
  field?: string;
  code?: string;
  message?: string;
};

export type ApiUiError = {
  status: number;
  code: string;
  title: string;
  message: string;
  details?: ApiErrorDetails[];
  actionType?: "login" | "retry" | "back" | "none";
};

export function parseApiError(error: unknown): ApiUiError {
  if (typeof error === "object" && error !== null) {
    const err = error as {
      status?: number;
      statusCode?: number;
      code?: string;
      message?: string;
      details?: ApiErrorDetails[];
      error?: {
        code?: string;
        message?: string;
        details?: ApiErrorDetails[];
      };
    };

    const status = err.status ?? err.statusCode ?? 500;
    const backendCode = err.error?.code ?? err.code ?? "unknown_error";
    const backendMessage = err.error?.message ?? err.message;
    const details = err.error?.details ?? err.details;

    switch (status) {
      case 401:
        return {
          status: 401,
          code: backendCode || "unauthorized",
          title: "Session Expired",
          message: backendMessage || "Your session has expired. Please sign in again.",
          actionType: "login",
        };
      case 403:
        return {
          status: 403,
          code: backendCode || "forbidden",
          title: "Access Denied",
          message:
            backendMessage ||
            "You do not have permission to view this resource or perform this action.",
          actionType: "back",
        };
      case 404:
        return {
          status: 404,
          code: backendCode || "not_found",
          title: "Resource Not Found",
          message: backendMessage || "The requested resource could not be found.",
          actionType: "back",
        };
      case 409:
        return {
          status: 409,
          code: backendCode || "conflict",
          title: "Conflict Detected",
          message:
            backendMessage ||
            "This record was updated by someone else or a duplicate action occurred. Please refresh.",
          actionType: "retry",
        };
      case 422:
        return {
          status: 422,
          code: backendCode || "validation_error",
          title: "Validation Error",
          message:
            backendMessage || "Some information is invalid. Please check the fields and try again.",
          details,
          actionType: "none",
        };
      case 429:
        return {
          status: 429,
          code: backendCode || "rate_limited",
          title: "Too Many Requests",
          message: backendMessage || "You are doing that too fast. Please wait a moment.",
          actionType: "retry",
        };
      default:
        return {
          status,
          code: backendCode || "internal_error",
          title: "Something Went Wrong",
          message:
            backendMessage || "An unexpected error occurred. Please try again or contact support.",
          actionType: "retry",
        };
    }
  }

  return {
    status: 500,
    code: "unknown_error",
    title: "Unexpected Error",
    message: String(error || "An unknown error occurred."),
    actionType: "retry",
  };
}
