import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Form input primitive module.
 * Provides a calm, low-friction interaction surface with clear focus state.
 */
export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-surface-cork bg-[#130b06] px-3 py-2 text-xs text-cream placeholder:text-cream-muted/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ember focus-visible:border-ember disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
