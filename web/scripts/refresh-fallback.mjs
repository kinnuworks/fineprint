// Saves current API responses for the hero models into public/fallback/.
// The site uses them only when the FinePrint API cannot be reached.
// Usage: NEXT_PUBLIC_API_BASE=http://localhost:8000 node scripts/refresh-fallback.mjs
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/+$/, "") + "/api";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "fallback");

export const HEROES = [
  "kenpath/svara-tts-v1",
  "ifmylove2011/girlslike",
  "unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit",
  "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
  "Qwen/Qwen2.5-7B-Instruct",
  "TheBloke/LeoScorpius-GreenNode-Alpaca-7B-v1-GGUF",
  "runwayml/stable-diffusion-v1-5",
  // Earlier demo models, kept so their links still work offline.
  "QCRI/Fanar-2-27B-Instruct",
  "meta-llama/Llama-3.1-8B-Instruct",
];
const READ_CARD = ["deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "TheBloke/LeoScorpius-GreenNode-Alpaca-7B-v1-GGUF"];

async function get(url, init) {
  const res = await fetch(url, { ...init, signal: AbortSignal.timeout(120000) });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

async function save(name, data) {
  await writeFile(path.join(OUT, name), JSON.stringify(data));
}

const enc = (id) => id.split("/").map(encodeURIComponent).join("/");
const slug = (id) => id.replaceAll("/", "__");

await mkdir(OUT, { recursive: true });
const bundle = { saved_at: new Date().toISOString(), models: {} };

const stats = await get(`${BASE}/stats`);
await save("stats.json", stats);
bundle.stats = stats;
for (const [key, url] of [
  ["load_bearing", `${BASE}/load-bearing?k=10`],
  ["relicense_points", `${BASE}/relicense-points?k=10`],
  ["what_if", `${BASE}/what-if`],
]) {
  bundle[key] = await get(url);
  await save(`${key}.json`, bundle[key]);
}

for (const id of HEROES) {
  const m = {};
  const tries = {
    report: `${BASE}/report/${enc(id)}?graph=true&use=commercial`,
    report_noncommercial: `${BASE}/report/${enc(id)}?graph=true&use=noncommercial`,
    nograph: `${BASE}/report/${enc(id)}?graph=false&use=commercial`,
    nograph_noncommercial: `${BASE}/report/${enc(id)}?graph=false&use=noncommercial`,
    descendants: `${BASE}/descendants/${enc(id)}?k=50`,
    substitutes: `${BASE}/substitutes/${enc(id)}?k=5`,
  };
  for (const [key, url] of Object.entries(tries)) {
    try {
      m[key] = await get(url);
      await save(`${slug(id)}.${key}.json`, m[key]);
    } catch (err) {
      console.warn(`skip ${key} for ${id}: ${err.message}`);
    }
  }
  if (READ_CARD.includes(id)) {
    try {
      m.readcard = await get(`${BASE}/read-card/${enc(id)}`, { method: "POST" });
      await save(`${slug(id)}.readcard.json`, m.readcard);
    } catch (err) {
      console.warn(`skip readcard for ${id}: ${err.message}`);
    }
  }
  bundle.models[id] = m;
  console.log(`saved ${id}: ${Object.keys(m).join(", ")}`);
}

await save("bundle.json", bundle);
console.log("wrote bundle.json");
