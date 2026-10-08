import type { ApiErrorBody } from '../types/api';

export class ApiError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly fields: string[];
  readonly status: number;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.code = body.code;
    this.retryable = body.retryable;
    this.fields = body.fields;
    this.status = status;
  }
}

function isErrorBody(value: unknown): value is { error: ApiErrorBody } {
  if (!value || typeof value !== 'object' || !('error' in value)) return false;
  const error = (value as { error: unknown }).error;
  return !!error && typeof error === 'object' && 'code' in error && 'message' in error;
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** 统一请求：后端错误格式转为 ApiError；网络中断、超时也给出可读的中文提示。 */
export async function requestJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort);
  let timedOut = false;
  const timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, options.timeoutMs ?? 15000);
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    const message = timedOut ? '请求超时，请稍后重试' : '无法连接后端，请确认后端已启动后重试';
    throw new ApiError({ code: timedOut ? 'TIMEOUT' : 'NETWORK', message, retryable: true, fields: [] }, 0);
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    if (isErrorBody(data)) throw new ApiError(data.error, response.status);
    throw new ApiError({
      code: `HTTP_${response.status}`,
      message: `服务暂时不可用（HTTP ${response.status}），请稍后重试`,
      retryable: response.status >= 500,
      fields: [],
    }, response.status);
  }
  return data as T;
}
