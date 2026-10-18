"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { search } from "@/lib/api";
import { compact, licClass, normalizeId } from "@/lib/format";
import type { SearchHit } from "@/lib/types";

/**
 * Model search with suggestions. Enter opens the report for the highlighted
 * suggestion, or for the id or Hugging Face URL as typed.
 */
export default function SearchBox({
  inputId,
  onPick,
  placeholder = "Model id or Hugging Face URL",
  showKbd = false,
}: {
  inputId?: string;
  /** When set, picking a model calls this instead of opening its report page. */
  onPick?: (id: string) => void;
  placeholder?: string;
  showKbd?: boolean;
}) {
  const router = useRouter();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const term = normalizeId(q);
    if (term.length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setStatus("loading");
      try {
        const res = await search(term, 8, ctrl.signal);
        setHits(res);
        setActive(-1);
        setStatus("idle");
      } catch (err) {
        if ((err as Error).name !== "AbortError") setStatus("error");
      }
    }, 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!showKbd) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) && !target.isContentEditable) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showKbd]);

  const go = (id: string) => {
    const clean = normalizeId(id);
    if (!clean) return;
    setOpen(false);
    if (onPick) onPick(clean);
    else router.push("/" + clean.split("/").map(encodeURIComponent).join("/"));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || hits.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % hits.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? hits.length - 1 : a - 1));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showList = open && normalizeId(q).length >= 2 && (hits.length > 0 || status === "error");

  return (
    <div className="search" ref={boxRef}>
      <form
        role="search"
        className="join"
        onSubmit={(e) => {
          e.preventDefault();
          go(active >= 0 && hits[active] ? hits[active].id : q);
        }}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder={placeholder}
          aria-label="Model id or Hugging Face URL"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {showKbd && !q && (
          <kbd aria-hidden="true" style={{ alignSelf: "center", marginRight: 4 }}>
            /
          </kbd>
        )}
        <button className="btn btn-ink" type="submit">
          Check
        </button>
      </form>
      {showList && (
        <ul className="suggest" id={listId} role="listbox">
          {status === "error" && hits.length === 0 ? (
            <li>
              <span className="muted">Search is unavailable. Press Check to open the id as typed.</span>
            </li>
          ) : (
            hits.map((h, i) => (
              <li
                key={h.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(h.id);
                }}
              >
                <span className="sid">{h.id}</span>
                <span className="meta">
                  <span className={licClass(h.license)}>{h.license ?? "no license"}</span>
                  {compact(h.downloads)}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
