import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-900",
          "placeholder:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900",
          "dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100",
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";
