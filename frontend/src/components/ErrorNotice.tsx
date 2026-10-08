import { ApiError } from '../api/client';

export default function ErrorNotice({ error, onRetry, retryLabel = '重试' }: {
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? '出现意外错误，请重试';
  const details = apiError?.fields.filter((f) => f && f !== message) ?? [];
  return (
    <div className="error-notice" role="alert">
      <div>
        <p>{message}</p>
        {details.length > 0 && (
          <ul>{details.slice(0, 4).map((detail) => <li key={detail}>{detail}</li>)}</ul>
        )}
      </div>
      {onRetry && <button type="button" onClick={onRetry}>{retryLabel}</button>}
    </div>
  );
}
