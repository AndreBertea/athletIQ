export const TRACK_COLOR_PALETTE: readonly string[] = [
  '#dc2626',
  '#2563eb',
  '#16a34a',
  '#ea580c',
  '#9333ea',
  '#0891b2',
  '#db2777',
  '#ca8a04',
];

export function trackColorForIndex(index: number): string {
  return TRACK_COLOR_PALETTE[index % TRACK_COLOR_PALETTE.length] ?? TRACK_COLOR_PALETTE[0] ?? '#dc2626';
}
