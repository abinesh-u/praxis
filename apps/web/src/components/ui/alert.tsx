import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Callout notification module.
 * Provides a structured visual container for execution notices and recovery guidance.
 */
const alertVariants = cva(
  "relative w-full rounded-xl border p-4 text-xs [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg+div]:translate-y-[-3px] [&:has(svg)]:pl-11",
  {
    variants: {
      variant: {
        default: "border-surface-cork bg-[#1a110a] text-cream",
        destructive: "border-red-900/60 bg-[#290d0a] text-red-200 [&>svg]:text-red-400",
        warning: "border-amber-800/60 bg-[#2b1706] text-amber-200 [&>svg]:text-amber-400",
        recovery: "border-[#dc5000]/60 bg-[#261005] text-[#ffedd7] [&>svg]:text-[#dc5000]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    role="alert"
    className={cn(alertVariants({ variant }), className)}
    {...props}
  />
));
Alert.displayName = "Alert";

const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={cn("mb-1 font-medium uppercase tracking-wider text-xs leading-none text-cream", className)}
    {...props}
  />
));
AlertTitle.displayName = "AlertTitle";

const AlertDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-xs text-cream-muted leading-relaxed [&_p]:leading-relaxed", className)}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { Alert, AlertTitle, AlertDescription };
