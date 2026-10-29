// Now Serving Seoul: the interest counter for email digests, added 29 October
// 2026, his call, to gauge interest before paying for a newsletter service.
// Everything else on the site is static assets; this Worker answers /api/*
// only (run_worker_first in wrangler.jsonc).
//
//   POST /api/interest          {"districts": ["GN", ...] or ["ALL"], "freq": "weekly"}
//   GET  /api/interest/totals   Authorization: Bearer <INTEREST_TOKEN>
//
// ⚠️ NO EMAIL ADDRESS, NO IP, NOTHING ABOUT THE VISITOR IS STORED: one KV key
// per vote, its choices in the key's metadata, so the totals are read from a
// key listing with no value reads. A key per vote rather than a counter
// because KV has no atomic increment, and two votes at once would lose one.
// The counts can be inflated by anyone who posts repeatedly; the page stops a
// second vote from the same browser, and that is all. Read them as a signal.

const DISTRICTS = ["GN", "JG", "JN", "MP", "SC", "SD", "SP", "YS"];
const FREQS = ["daily", "weekly", "monthly"];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export function validate(body) {
  if (!body || typeof body !== "object") return "expected a JSON object";
  const { districts, freq } = body;
  if (!FREQS.includes(freq)) return "freq must be daily, weekly or monthly";
  if (!Array.isArray(districts) || districts.length === 0) return "pick at least one district";
  const all = districts.length === 1 && districts[0] === "ALL";
  if (!all && !districts.every((d) => DISTRICTS.includes(d))) return "unknown district";
  if (new Set(districts).size !== districts.length) return "a district is repeated";
  return null;
}

export function tally(metas) {
  const t = { votes: 0, freq: {}, districts: {} };
  for (const m of metas) {
    if (!m || !FREQS.includes(m.f) || !Array.isArray(m.d)) continue;
    t.votes += 1;
    t.freq[m.f] = (t.freq[m.f] || 0) + 1;
    for (const d of m.d) t.districts[d] = (t.districts[d] || 0) + 1;
  }
  return t;
}

async function vote(request, env) {
  const text = await request.text();
  if (text.length > 1000) return json({ error: "too large" }, 413);
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return json({ error: "expected JSON" }, 400);
  }
  const err = validate(body);
  if (err) return json({ error: err }, 400);
  const key = `v:${new Date().toISOString()}:${crypto.randomUUID()}`;
  await env.INTEREST.put(key, "1", { metadata: { d: body.districts, f: body.freq } });
  return json({ ok: true });
}

async function totals(request, env) {
  const auth = request.headers.get("authorization") || "";
  if (!env.INTEREST_TOKEN || auth !== `Bearer ${env.INTEREST_TOKEN}`) {
    return json({ error: "unauthorized" }, 401);
  }
  const metas = [];
  let cursor;
  do {
    const page = await env.INTEREST.list({ prefix: "v:", cursor });
    for (const k of page.keys) metas.push(k.metadata);
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return json(tally(metas));
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === "/api/interest" && request.method === "POST") return vote(request, env);
    if (pathname === "/api/interest/totals" && request.method === "GET") return totals(request, env);
    if (pathname.startsWith("/api/")) return json({ error: "not found" }, 404);
    return env.ASSETS.fetch(request);
  },
};
