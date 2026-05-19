import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { motion, type HTMLMotionProps } from "motion/react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "relative inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-zinc-50 text-zinc-950 hover:bg-zinc-200 shadow-[0_1px_0_0_rgba(255,255,255,0.1)_inset,0_-1px_0_0_rgba(0,0,0,0.2)_inset,0_4px_12px_-2px_rgba(0,0,0,0.4)]",
        secondary:
          "bg-zinc-900 text-zinc-100 hover:bg-zinc-800 border border-zinc-800",
        outline:
          "border border-zinc-800 bg-transparent hover:bg-zinc-900 hover:text-zinc-50 text-zinc-300",
        ghost: "hover:bg-zinc-900 text-zinc-300 hover:text-zinc-50",
        destructive: "bg-red-950 text-red-100 hover:bg-red-900 border border-red-900/50",
        link: "text-zinc-100 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type MotionButtonProps = HTMLMotionProps<"button">;

export interface ButtonProps
  extends Omit<MotionButtonProps, "ref">,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    if (asChild) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { children, ...rest } = props as any;
      return (
        <Slot
          className={cn(buttonVariants({ variant, size, className }))}
          ref={ref}
          {...rest}
        >
          {children}
        </Slot>
      );
    }
    return (
      <motion.button
        ref={ref}
        whileTap={{ scale: 0.97 }}
        transition={{ duration: 0.15, ease: [0.32, 0.72, 0, 1] }}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
