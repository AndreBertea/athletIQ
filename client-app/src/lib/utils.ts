import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * `cn()` — concat Tailwind classes with conflict resolution.
 * Pattern shadcn standard. Use everywhere classes are conditional.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
