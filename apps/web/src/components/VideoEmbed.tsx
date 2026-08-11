"use client";

export function VideoEmbed({
  provider,
  embedUrl,
  fallbackUrl,
  title,
}: {
  provider?: string | null;
  embedUrl?: string | null;
  fallbackUrl?: string | null;
  title?: string;
}) {
  if (!embedUrl && !fallbackUrl) return null;

  if (embedUrl && (provider === "youtube" || provider === "bilibili")) {
    return (
      <div className="relative aspect-video w-full overflow-hidden bg-black/5">
        <iframe
          title={title || "video"}
          src={embedUrl}
          className="absolute inset-0 h-full w-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          referrerPolicy="no-referrer-when-downgrade"
        />
      </div>
    );
  }

  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--body)]">
      仅外链播放
      {fallbackUrl ? (
        <>
          ：
          <a className="text-[var(--accent)] underline" href={fallbackUrl} target="_blank" rel="noreferrer">
            打开原页
          </a>
        </>
      ) : null}
    </div>
  );
}
