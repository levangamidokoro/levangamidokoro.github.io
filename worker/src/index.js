// 見どころなう 受付窓口（Cloudflare Workers + D1）
//
// 公開（ページから呼ぶ）
//   GET  /api/vapid        通知用の公開鍵
//   POST /api/subscribe    通知の登録   POST /api/unsubscribe  通知の解除
//   POST /api/hit          ページの表示を1回数える（Cookieは使わない）
//   GET  /api/live         試合中の「いまの熱さ」（ページが20秒ごとに読む）
// 閲覧用トークンが必要
//   GET  /api/stats        アクセス数・通知登録数の集計
// GitHub Actions だけが呼べる（GitHubが発行する本人証明トークン＝OIDCで確認。合言葉の共有は不要）
//   POST /api/notify       登録者全員にWebプッシュを送る（40件ずつ。cursor を返すので続きを呼ぶ）
//   POST /api/live         「いまの熱さ」を置く（収集プログラムが20秒ごとに呼ぶ）
//
// 環境変数：ALLOW_ORIGIN, ALLOW_REPO（vars）
// シークレット：VAPID_PUBLIC, VAPID_PRIVATE_JWK, STATS_TOKEN, HASH_SALT（初回デプロイ時に自動で作る。STATS_TOKENだけは本人が決める）

const KEEP_DAYS = 40;
const MAX_BODY = 8 * 1024;
const MAX_SUBS = 50000;

const jst = (t = Date.now()) => new Date(t + 9 * 3600e3);
const today = () => jst().toISOString().slice(0, 10);
const daysAgo = (n) => jst(Date.now() - n * 86400e3).toISOString().slice(0, 10);

function cors(env, req) {
  const origin = req.headers.get("Origin") || "";
  const ok = origin === env.ALLOW_ORIGIN || origin.startsWith("http://localhost") || origin.startsWith("http://127.0.0.1");
  return {
    "Access-Control-Allow-Origin": ok ? origin : env.ALLOW_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

const json = (data, status, headers) =>
  new Response(JSON.stringify(data), { status, headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });

async function body(req) {
  const text = await req.text();
  if (text.length > MAX_BODY) throw new Error("too large");
  return JSON.parse(text || "{}");
}

function authed(req, token) {
  const h = req.headers.get("Authorization") || "";
  return token && h === `Bearer ${token}`;
}

async function bump(env, kind, n = 1, day = today()) {
  if (!n) return;
  await env.DB.prepare(
    "INSERT INTO events (day, kind, n) VALUES (?1, ?2, ?3) ON CONFLICT(day, kind) DO UPDATE SET n = n + ?3"
  ).bind(day, kind, n).run();
}

function device(ua) {
  if (/iPhone|iPad|iPod/.test(ua)) return "iPhone";
  if (/Android/.test(ua)) return "Android";
  return "PC";
}

async function sha(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].slice(0, 12).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function validSub(s) {
  return s && typeof s.endpoint === "string" && s.endpoint.startsWith("https://") && s.endpoint.length < 1000
    && s.keys && typeof s.keys.p256dh === "string" && typeof s.keys.auth === "string"
    && s.keys.p256dh.length < 200 && s.keys.auth.length < 100;
}

async function purge(env) {
  const cut = daysAgo(KEEP_DAYS);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM visitors WHERE day < ?1").bind(cut),
  ]);
}

async function stats(env) {
  const from = daysAgo(KEEP_DAYS - 1);
  const ev = await env.DB.prepare("SELECT day, kind, n FROM events WHERE day >= ?1 ORDER BY day").bind(from).all();
  const uv = await env.DB.prepare("SELECT day, COUNT(*) AS n FROM visitors WHERE day >= ?1 GROUP BY day").bind(from).all();
  const subs = await env.DB.prepare("SELECT device, COUNT(*) AS n FROM subs GROUP BY device").all();
  const total = await env.DB.prepare("SELECT kind, SUM(n) AS n FROM events GROUP BY kind").all();
  const days = {};
  for (let i = KEEP_DAYS - 1; i >= 0; i--) days[daysAgo(i)] = { day: daysAgo(i), view: 0, uniq: 0, sub: 0, unsub: 0, gone: 0, push_sent: 0, push_fail: 0 };
  for (const r of ev.results) if (days[r.day]) days[r.day][r.kind] = r.n;
  for (const r of uv.results) if (days[r.day]) days[r.day].uniq = r.n;
  const byDevice = Object.fromEntries(subs.results.map((r) => [r.device || "不明", r.n]));
  return {
    generated: jst().toISOString().slice(0, 16).replace("T", " "),
    subscribers: Object.values(byDevice).reduce((a, b) => a + b, 0),
    by_device: byDevice,
    totals: Object.fromEntries(total.results.map((r) => [r.kind, r.n])),
    days: Object.values(days),
  };
}

// ---------- Webプッシュの送信（RFC 8291 aes128gcm ＋ VAPID） ----------
const enc = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const cat = (...parts) => { const out = new Uint8Array(parts.reduce((a, p) => a + p.length, 0)); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; } return out; };

async function hkdf(salt, ikm, info, bytes) {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt, info }, key, bytes * 8));
}

async function encrypt(sub, payload) {
  const uaPub = unb64u(sub.p256dh), auth = unb64u(sub.auth);
  const local = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
  const asPub = new Uint8Array(await crypto.subtle.exportKey("raw", local.publicKey));
  const peer = await crypto.subtle.importKey("raw", uaPub, { name: "ECDH", namedCurve: "P-256" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: peer }, local.privateKey, 256));
  const ikm = await hkdf(auth, shared, cat(enc.encode("WebPush: info\0"), uaPub, asPub), 32);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, enc.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, enc.encode("Content-Encoding: nonce\0"), 12);
  const key = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, cat(enc.encode(payload), new Uint8Array([2]))));
  const rs = new Uint8Array([0, 0, 16, 0]);   // レコードサイズ 4096
  return cat(salt, rs, new Uint8Array([asPub.length]), asPub, ct);
}

let vapidKey = null;
async function vapidHeader(env, endpoint) {
  if (!vapidKey) vapidKey = await crypto.subtle.importKey("jwk", JSON.parse(env.VAPID_PRIVATE_JWK), { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const head = b64u(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const claims = b64u(enc.encode(JSON.stringify({ aud: new URL(endpoint).origin, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: env.VAPID_CONTACT || "mailto:midokoro@users.noreply.github.com" })));
  const sig = b64u(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, vapidKey, enc.encode(`${head}.${claims}`)));
  return `vapid t=${head}.${claims}.${sig}, k=${env.VAPID_PUBLIC}`;
}

async function pushOne(env, sub, payload) {
  const res = await fetch(sub.endpoint, {
    method: "POST",
    headers: { Authorization: await vapidHeader(env, sub.endpoint), TTL: "600", Urgency: "high",
               "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream" },
    body: await encrypt(sub, payload),
  });
  return res.status;
}

// ---------- GitHub Actions の本人確認（OIDC） ----------
let jwks = null;
async function githubOk(env, req) {
  const tok = (req.headers.get("Authorization") || "").replace(/^Bearer /, "");
  if (env.DEV_NOTIFY_TOKEN && tok === env.DEV_NOTIFY_TOKEN) return true;   // ローカル試験用（本番では未設定）
  const parts = tok.split(".");
  if (parts.length !== 3) return false;
  const head = JSON.parse(new TextDecoder().decode(unb64u(parts[0])));
  const claims = JSON.parse(new TextDecoder().decode(unb64u(parts[1])));
  if (claims.iss !== "https://token.actions.githubusercontent.com" || claims.aud !== "midokoro-api"
      || claims.repository !== env.ALLOW_REPO || !(claims.exp > Date.now() / 1000)) return false;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (!jwks || attempt) jwks = (await (await fetch("https://token.actions.githubusercontent.com/.well-known/jwks")).json()).keys;
    const jwk = jwks.find((k) => k.kid === head.kid);
    if (!jwk) continue;
    const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, unb64u(parts[2]), enc.encode(`${parts[0]}.${parts[1]}`));
  }
  return false;
}

const BATCH = 40;   // 無料プランは1回の呼び出しで外部への送信が50件まで

// ---------- 試合中の「いまの熱さ」 ----------
const LIVE_MAX_AGE = 4 * 3600;            // 4時間より古いものは返さない
let liveMemo = { t: 0, v: null };         // 同じ場所への問い合わせが続いたら、5秒だけ使い回す
const str = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");
const int = (v, lo, hi) => (Number.isFinite(+v) ? Math.max(lo, Math.min(hi, Math.round(+v))) : null);

function cleanLive(r) {                    // 決まった項目だけを、長さと形をそろえて残す
  const key = /^[0-9a-z_-]{1,20}$/i.test(String(r.key || "")) ? String(r.key) : null;
  const url = /^https:\/\/www\.bleague\.jp\//.test(String(r.url || "")) ? str(r.url, 200) : "";
  const level = ["高", "中", "低"].includes(r.level) ? r.level : "";
  if (!key) return null;
  return { key, status: str(r.status, 10), level, meter: int(r.meter, 0, 100), pct: int(r.pct, 0, 100),
           clock: str(r.clock, 20), text: str(r.text, 200), opponent: str(r.opponent, 20), url,
           at: int(r.at, 0, 4102444800) || Math.floor(Date.now() / 1000) };
}

async function readLive(env) {
  if (Date.now() - liveMemo.t < 5000) return liveMemo.v;
  const row = await env.DB.prepare("SELECT body, at FROM live WHERE id = 1").first();
  const v = row && Date.now() / 1000 - row.at < LIVE_MAX_AGE ? JSON.parse(row.body) : null;
  liveMemo = { t: Date.now(), v };
  return v;
}

export default {
  async fetch(req, env) {
    const h = cors(env, req);
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    try {
      if (url.pathname === "/api/vapid" && req.method === "GET") {
        return json({ key: env.VAPID_PUBLIC || "" }, 200, h);
      }
      if (url.pathname === "/api/subscribe" && req.method === "POST") {
        const s = await body(req);
        if (!validSub(s)) return json({ ok: false }, 400, h);
        const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM subs").first("n");
        if (count >= MAX_SUBS) return json({ ok: false, error: "full" }, 503, h);
        const exists = await env.DB.prepare("SELECT 1 AS x FROM subs WHERE endpoint = ?1").bind(s.endpoint).first("x");
        if (exists) {
          await env.DB.prepare("UPDATE subs SET p256dh = ?2, auth = ?3 WHERE endpoint = ?1")
            .bind(s.endpoint, s.keys.p256dh, s.keys.auth).run();
        } else {
          await env.DB.prepare("INSERT INTO subs (endpoint, p256dh, auth, device, created) VALUES (?1, ?2, ?3, ?4, ?5)")
            .bind(s.endpoint, s.keys.p256dh, s.keys.auth, device(req.headers.get("User-Agent") || ""), today()).run();
          await bump(env, "sub");
        }
        return json({ ok: true }, 200, h);
      }
      if (url.pathname === "/api/unsubscribe" && req.method === "POST") {
        const s = await body(req);
        const res = await env.DB.prepare("DELETE FROM subs WHERE endpoint = ?1").bind(String(s.endpoint || "")).run();
        if (res.meta.changes) await bump(env, "unsub");
        return json({ ok: true }, 200, h);
      }
      if (url.pathname === "/api/hit" && req.method === "POST") {
        const origin = req.headers.get("Origin") || "";
        if (origin && origin !== env.ALLOW_ORIGIN && !origin.startsWith("http://localhost") && !origin.startsWith("http://127.0.0.1")) {
          return new Response(null, { status: 204, headers: h });
        }
        const ip = req.headers.get("CF-Connecting-IP") || "";
        const ua = req.headers.get("User-Agent") || "";
        if (/bot|crawl|spider|preview/i.test(ua)) return new Response(null, { status: 204, headers: h });
        const day = today();
        await bump(env, "view", 1, day);
        const v = await sha(`${day}|${ip}|${ua}|${env.HASH_SALT || ""}`);
        await env.DB.prepare("INSERT OR IGNORE INTO visitors (day, h) VALUES (?1, ?2)").bind(day, v).run();
        return new Response(null, { status: 204, headers: h });
      }
      if (url.pathname === "/api/live" && req.method === "GET") {
        return json({ ok: true, live: await readLive(env) }, 200, h);
      }
      if (url.pathname === "/api/live" && req.method === "POST") {
        if (!(await githubOk(env, req))) return json({ ok: false }, 401, h);
        const v = cleanLive(await body(req));
        if (!v) return json({ ok: false }, 400, h);
        await env.DB.prepare("INSERT INTO live (id, body, at) VALUES (1, ?1, ?2) ON CONFLICT(id) DO UPDATE SET body = ?1, at = ?2")
          .bind(JSON.stringify(v), v.at).run();
        liveMemo = { t: Date.now(), v };
        return json({ ok: true }, 200, h);
      }
      if (url.pathname === "/api/stats" && req.method === "GET") {
        if (!authed(req, env.STATS_TOKEN)) return json({ ok: false }, 401, h);
        return json(await stats(env), 200, h);
      }
      if (url.pathname === "/api/notify" && req.method === "POST") {
        if (!(await githubOk(env, req))) return json({ ok: false }, 401, h);
        const r = await body(req);
        const payload = JSON.stringify({ title: String(r.title || "見どころなう"), body: String(r.body || ""), url: String(r.url || "./") });
        const cursor = Number(url.searchParams.get("cursor") || 0);
        const rows = (await env.DB.prepare("SELECT rowid AS id, endpoint, p256dh, auth FROM subs WHERE rowid > ?1 ORDER BY rowid LIMIT ?2").bind(cursor, BATCH).all()).results;
        let sent = 0, failed = 0; const gone = [], why = [];
        const queue = rows.slice();
        await Promise.all(Array.from({ length: 6 }, async () => {   // 同時接続は6本まで（Workersの制限）
          for (let s; (s = queue.shift()); ) {
          try {
            let st;
            try { st = await pushOne(env, s, payload); }
            catch (e) { st = await pushOne(env, s, payload); }      // 通信の切断は1回だけやり直す
            if (st >= 200 && st < 300) sent++;
            else if (st === 404 || st === 410) gone.push(s.endpoint);
            else { failed++; why.push(String(st)); }
          } catch (e) { failed++; why.push(String(e && e.message || e).slice(0, 80)); }
          }
        }));
        for (const ep of gone) await env.DB.prepare("DELETE FROM subs WHERE endpoint = ?1").bind(ep).run();
        await bump(env, "gone", gone.length);
        await bump(env, "push_sent", sent);
        await bump(env, "push_fail", failed);
        const next = rows.length === BATCH ? rows[rows.length - 1].id : null;
        return json({ ok: true, sent, failed, gone: gone.length, cursor: next, ...(env.DEV_NOTIFY_TOKEN ? { why: why.slice(0, 5) } : {}) }, 200, h);
      }
      return json({ ok: false }, 404, h);
    } catch (e) {
      return json({ ok: false }, 500, h);
    }
  },
  async scheduled(_ev, env) {
    await purge(env);
  },
};
