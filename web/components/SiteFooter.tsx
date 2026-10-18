import Link from "next/link";
import AppIcon from "./AppIcon";
import { REPO_URL } from "@/lib/site";

export default function SiteFooter() {
  return (
    <footer className="footer">
      <div className="container">
        <Link href="/" className="footer__brand">
          <AppIcon />
          FinePrint
        </Link>
        <div className="footer__links">
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
          <span>Data: Hugging Face Hub metadata (Apache-2.0)</span>
          <span>Not legal advice</span>
          <span>Built on FalkorDB for Graph Hacks 2026</span>
        </div>
      </div>
    </footer>
  );
}
