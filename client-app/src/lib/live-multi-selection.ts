export const LIVE_MULTI_SELECTION_STORAGE_KEY = 'agon.live.multiSessionIds';
export const LIVE_MULTI_SELECTION_EVENT = 'agon-live-multi-selection-change';

export function readLiveMultiSessionIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    return normalizeSessionIds(
      JSON.parse(window.localStorage.getItem(LIVE_MULTI_SELECTION_STORAGE_KEY) ?? '[]'),
    );
  } catch {
    return [];
  }
}

export function writeLiveMultiSessionIds(ids: string[]): string[] {
  const normalized = normalizeSessionIds(ids);
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(
      LIVE_MULTI_SELECTION_STORAGE_KEY,
      JSON.stringify(normalized),
    );
    window.dispatchEvent(
      new CustomEvent(LIVE_MULTI_SELECTION_EVENT, { detail: normalized }),
    );
  }
  return normalized;
}

export function toggleLiveMultiSessionId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}

export function removeLiveMultiSessionId(ids: string[], id: string): string[] {
  return ids.filter((item) => item !== id);
}

function normalizeSessionIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(
    new Set(
      value.filter((item): item is string => typeof item === 'string' && item.length > 0),
    ),
  );
}
