import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Class name merging utility module.
 * Provides an interface to leverage clsx and tailwind-merge with high locality.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
