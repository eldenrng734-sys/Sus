import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/**
 * buttonVariants — class-variance-authority schema for the Button component.
 *
 * Animation / interaction notes
 * ─────────────────────────────
 * • `transition-[color,background-color,border-color,box-shadow,transform,opacity]`
 *   replaces the original `transition-all`.
 *
 *   `transition-all` generates `transition-property: all`, which is immediately
 *   overridden by the global `button { transition-property: … }` rule in
 *   globals.css (plain CSS comes after the Tailwind layer in the cascade).
 *   The result is that Tailwind's own transition utility loses the race and the
 *   button's timing curve / duration are both discarded — the global 160 ms /
 *   cubic-bezier rule wins instead.
 *
 *   By listing the exact same properties the global rule lists (plus `outline`
 *   for the border-based focus ring) we produce an identical result *and* give
 *   Tailwind the chance to control duration/easing via additional utilities when
 *   needed, without depending on `all`.
 *
 * • `outline-none` is kept — the button manages focus visibility itself through
 *   `focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50`.
 *   The global `button:focus-visible { outline: 2px solid #3b82f6 }` rule in
 *   globals.css must NOT fire for this component because it is a hard-coded
 *   colour that bypasses the design token and cannot animate (outline is not
 *   transitioable in CSS). `outline-none` wins here — it has equal specificity
 *   but higher source order inside the Tailwind layer, so it takes precedence.
 *
 *   However `outline-none` from Tailwind's base layer sets `outline: none`.
 *   The global plain-CSS rule `button:focus-visible { outline: … }` has equal
 *   element-selector specificity but comes *after* the Tailwind layer, so it
 *   OVERRIDES `outline-none` for keyboard focus — causing a sudden hard-edged
 *   blue outline to appear on top of the box-shadow ring.
 *
 *   Fix: use `focus-visible:outline-none` (applies at the same cascade layer as
 *   the global rule but as an inline utility it has higher specificity via the
 *   Tailwind utility class) so the browser cannot fall back to the global outline.
 *
 * • `active:not-aria-[haspopup]:translate-y-px` — 1 px press-down feedback.
 *   Requires `transform` in transition-property to ease smoothly (now included).
 */
const buttonVariants = cva(
  [
    // Layout & base
    "group/button inline-flex shrink-0 items-center justify-center",
    "rounded-lg border border-transparent bg-clip-padding",
    "text-sm font-medium whitespace-nowrap",
    "select-none",

    // ── Transition ──────────────────────────────────────────────────────────
    // Explicit property list instead of `transition-all` so the Tailwind utility
    // is not silently overridden by the global `button { transition-property }` rule.
    // Includes `outline` so the focus-border animates; `box-shadow` for the ring;
    // `transform` for the active:translate-y-px press feedback.
    "transition-[color,background-color,border-color,box-shadow,outline,transform,opacity]",
    "duration-[160ms]",
    "ease-[cubic-bezier(0.2,0,0,1)]",

    // ── Focus ────────────────────────────────────────────────────────────────
    // `focus-visible:outline-none` overrides the global `button:focus-visible
    // { outline: 2px solid #3b82f6 }` plain-CSS rule (higher specificity via
    // Tailwind's utility class) so only the box-shadow ring is shown — no
    // competing hard-coded outline flash.
    "focus-visible:outline-none",
    "focus-visible:border-ring",
    "focus-visible:ring-3",
    "focus-visible:ring-ring/50",

    // ── Press feedback ───────────────────────────────────────────────────────
    "active:not-aria-[haspopup]:translate-y-px",

    // ── Reduced motion ────────────────────────────────────────────────────────
    "motion-reduce:transition-none motion-reduce:transform-none",

    // ── Disabled ─────────────────────────────────────────────────────────────
    "disabled:pointer-events-none disabled:opacity-50",

    // ── Validation ───────────────────────────────────────────────────────────
    "aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
    "dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",

    // ── SVG children ─────────────────────────────────────────────────────────
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/80",
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
