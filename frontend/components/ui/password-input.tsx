"use client";

import { forwardRef, useState, type InputHTMLAttributes } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  /** Used in the toggle's accessible name, e.g. "Show current password". */
  visibilityLabel: string;
};

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, visibilityLabel, ...props }, ref) => {
    const [isVisible, setIsVisible] = useState(false);
    return (
      <div className="relative">
        <Input
          ref={ref}
          type={isVisible ? "text" : "password"}
          className={cn("pr-16", className)}
          {...props}
        />
        <button
          type="button"
          onClick={() => setIsVisible((visible) => !visible)}
          aria-label={`${isVisible ? "Hide" : "Show"} ${visibilityLabel}`}
          aria-pressed={isVisible}
          className="absolute inset-y-0 right-0 flex items-center rounded-r-md px-3 text-xs font-medium text-zinc-600 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          {isVisible ? "Hide" : "Show"}
        </button>
      </div>
    );
  }
);
PasswordInput.displayName = "PasswordInput";
