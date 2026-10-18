"use client";

/** Scrolls to the model search and focuses it. */
export default function CheckButton({ className = "btn btn-ink btn-lg", label = "Check a model" }) {
  return (
    <a
      href="#check"
      className={className}
      onClick={(e) => {
        const input = document.getElementById("model-search") as HTMLInputElement | null;
        if (!input) return;
        e.preventDefault();
        input.scrollIntoView({ behavior: "smooth", block: "center" });
        input.focus({ preventScroll: true });
      }}
    >
      {label}
    </a>
  );
}
