// Adapted from Beautiful UI's Button (MIT, see LICENSE-beautiful-ui.txt):
// pill buttons with a pressed scale. Plain variant map instead of cva.

import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "accent" | "success" | "quiet";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-ink text-white hover:opacity-90",
  secondary: "bg-surface text-ink shadow-btn hover:bg-inset aria-expanded:bg-hover",
  accent: "bg-accent-strong text-white hover:opacity-90",
  success: "bg-green-ink text-white",
  quiet: "text-ink-2 hover:bg-hover hover:text-ink",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      type="button"
      className={`inline-flex h-[27px] items-center justify-center gap-1.5 rounded-full px-3
        text-[12.5px] font-medium leading-none select-none
        transition-[transform,background-color,opacity] duration-150 ease-out
        active:scale-[0.96] disabled:pointer-events-none disabled:opacity-50
        focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent
        ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
