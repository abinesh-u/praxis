import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Interactive button primitive module.
 * Provides a flexible styling interface with strong visual locality.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap text-xs font-medium uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-surface-bark text-cream hover:bg-[#4a301e] border border-surface-cork rounded-pill px-5 py-2.5",
        outline:
          "border border-cream/40 bg-transparent text-cream hover:border-cream hover:bg-white/5 rounded-outline px-4 py-2",
        ghost:
          "bg-transparent text-cream hover:bg-surface-bark/40 hover:text-cream rounded-md px-3 py-2",
        destructive:
          "border border-red-900/60 bg-[#2d0b08] text-cream hover:bg-[#3d0f0a] rounded-outline px-4 py-2",
        secondary:
          "bg-surface-card border border-surface-cork text-cream hover:bg-surface-bark/60 rounded-outline px-4 py-2",
      },
      size: {
        default: "h-9",
        sm: "h-8 px-3 text-[11px]",
        lg: "h-11 px-7 text-sm",
        icon: "h-9 w-9 p-0 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
