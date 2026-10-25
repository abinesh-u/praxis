import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Status indicator badge module.
 * Exposes an interface for communicating workflow state and risk level.
 */
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-surface-cork bg-surface-card text-cream",
        secondary:
          "border-surface-cork/60 bg-transparent text-cream-muted",
        low:
          "border-surface-cork bg-[#1e130b] text-cream-muted",
        medium:
          "border-amber-700/60 bg-amber-950/40 text-amber-200",
        high:
          "border-[#dc5000]/70 bg-[#dc5000]/20 text-[#ffb088]",
        success:
          "border-emerald-800/60 bg-emerald-950/40 text-emerald-300",
        destructive:
          "border-red-800/60 bg-red-950/40 text-red-300",
        warning:
          "border-amber-600/60 bg-amber-950/40 text-amber-300",
        accent:
          "border-[#dc5000]/80 bg-[#382416] text-[#ffedd7]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
