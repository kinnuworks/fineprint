import Link from "next/link";
import AppIcon from "./AppIcon";
import { REPO_URL } from "@/lib/site";

export default function SiteNav() {
  return (
    <nav className="nav" aria-label="Main">
      <div className="nav__bar">
        <Link href="/" className="nav__brand">
          <AppIcon />
          FinePrint
        </Link>
        <div className="nav__links">
          <Link href="/#how">How it works</Link>
          <Link href="/#findings">Findings</Link>
          <Link href="/#agents">For agents</Link>
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
        <div className="nav__end">
          <Link href="/#check" className="btn btn-ink btn-sm">
            Check a model
          </Link>
        </div>
      </div>
    </nav>
  );
}
