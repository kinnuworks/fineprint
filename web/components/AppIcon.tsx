/** FinePrint app icon: a cream document tile with ink lines and a small terracotta seal. */
export default function AppIcon({ className = "app-icon", title }: { className?: string; title?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <rect width="64" height="64" rx="14.4" fill="#FBF3E6" />
      <rect x="0.5" y="0.5" width="63" height="63" rx="14" fill="none" stroke="#17150F" strokeOpacity=".12" />
      <path
        d="M18 12h20l10 10v30a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2V14a2 2 0 0 1 2-2z"
        fill="#FFFEFC"
        stroke="#17150F"
        strokeOpacity=".22"
      />
      <path d="M38 12v8a2 2 0 0 0 2 2h8" fill="none" stroke="#17150F" strokeOpacity=".22" />
      <rect x="22" y="24" width="14" height="3" rx="1.5" fill="#17150F" />
      <rect x="22" y="31" width="20" height="2.4" rx="1.2" fill="#17150F" fillOpacity=".55" />
      <rect x="22" y="36.5" width="17" height="2.4" rx="1.2" fill="#17150F" fillOpacity=".55" />
      <rect x="22" y="42" width="9" height="2" rx="1" fill="#17150F" fillOpacity=".35" />
      <circle cx="42" cy="45" r="7" fill="#D66B38" />
      <circle cx="42" cy="45" r="4.4" fill="none" stroke="#FFFEFC" strokeWidth="1.4" />
    </svg>
  );
}
