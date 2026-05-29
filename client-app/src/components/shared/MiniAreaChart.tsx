import { useId } from 'react';
import { cn } from '@/lib/utils';

interface MiniAreaChartProps {
  data: Array<number | null | undefined>;
  color?: string;
  height?: number;
  className?: string;
}

export default function MiniAreaChart({
  data,
  color = '#9C49F5',
  height = 64,
  className,
}: MiniAreaChartProps) {
  const gradientId = useId().replace(/:/g, '');
  const points = data.filter((value): value is number => Number.isFinite(value));

  if (points.length < 2) {
    return <div className={cn('rounded-[10px] bg-[var(--glass-tile)]', className)} style={{ height }} />;
  }

  const width = 320;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const spread = max - min || 1;
  const step = width / Math.max(1, points.length - 1);
  const top = 6;
  const bottom = height - 6;
  const coords = points.map((value, index) => {
    const x = index * step;
    const y = bottom - ((value - min) / spread) * (bottom - top);
    return [x, y] as const;
  });
  const line = coords.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const area = `0,${height} ${line} ${width},${height}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn('block w-full overflow-visible rounded-[10px]', className)}
      style={{ height }}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={area} fill={`url(#${gradientId})`} />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
