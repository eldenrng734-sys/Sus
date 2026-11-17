export interface ApiSuccess<T> {
  data: T;
}

export interface PaginationMeta {
  next_cursor: string | null;
  has_more: boolean;
}

export interface ApiListSuccess<T> {
  data: T[];
  meta: PaginationMeta;
}

export interface ApiErrorDetail {
  field?: string;
  code: string;
  message: string;
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[] | Record<string, unknown> | null;
    request_id?: string | null;
  };
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorResponse["error"]["details"];
  readonly requestId?: string | null;

  constructor(
    status: number,
    error: ApiErrorResponse["error"],
  ) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = error.code;
    this.details = error.details;
    this.requestId = error.request_id;
  }
}
