import { clsx } from "clsx";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center font-medium rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none",
        size === "sm" && "text-sm px-3 py-1.5",
        size === "md" && "text-sm px-4 py-2",
        variant === "primary" &&
          "bg-slate-900 text-white hover:bg-slate-700",
        variant === "secondary" &&
          "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50",
        variant === "ghost" &&
          "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
