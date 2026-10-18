export const REPO_URL = (process.env.NEXT_PUBLIC_REPO_URL || "https://github.com/kinnuworks/fineprint").replace(
  /\/+$/,
  "",
);
export const AGENT_README = `${REPO_URL}/blob/main/agent/README.md`;
export const modelHref = (id: string) => "/" + id.split("/").map(encodeURIComponent).join("/");
