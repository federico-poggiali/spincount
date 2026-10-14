import { useEffect, useRef, useState, type CSSProperties } from "react";

const OPEN: CSSProperties = { display: "block", WebkitLineClamp: "unset", overflow: "visible" };

/** A note cropped by its stylesheet's line clamp. Only when the text is actually cut does it
 * become a button that shows the whole note; a note that fits is plain text. */
export function ClampedNote({ text, className, as: Tag = "p" }: { text: string; className: string; as?: "p" | "em" }) {
  const ref = useRef<HTMLElement>(null);
  const [cut, setCut] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      if (!open) setCut(el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, open]);

  const clickable = cut || open;
  return (
    <Tag ref={ref as never} className={className} style={open ? OPEN : undefined}
      {...(clickable ? {
        role: "button", tabIndex: 0, "aria-expanded": open, title: open ? "Show less" : "Show the whole note",
        onClick: () => setOpen(!open),
        onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open); } },
      } : {})}>
      {text}
    </Tag>
  );
}
