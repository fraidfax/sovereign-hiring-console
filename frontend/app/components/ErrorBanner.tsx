export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-red-500/40 bg-red-950/60 px-4 py-3 text-sm text-red-200"
    >
      <span aria-hidden className="mt-0.5 text-lg leading-none">
        ⚠
      </span>
      <span>{message}</span>
    </div>
  );
}
