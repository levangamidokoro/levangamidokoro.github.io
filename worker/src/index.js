// 見どころなう 受付窓口（Cloudflare Workers + D1）
//
// 公開（ページから呼ぶ）
//   GET  /api/vapid        通知用の公開鍵
//   POST /api/subscribe    通知の登録   POST /api/unsubscribe  通知の解除
//   POST /api/hit          ページの表示を1回数える（Cookieは使わない）
//   GET  /api/live         試合中の「いまの熱さ」（ページが20秒ごとに読む）
// 閲覧用トークンが必要
//   GET  /api/stats        アクセス数・通知登録数・試合ごとの通知とタップの集計
//   GET  /api/go           通知のタップを数えて、B.LEAGUE公式の試合ページへ移す（?g=試合番号&k=full|geki）
// GitHub Actions だけが呼べる（GitHubが発行する本人証明トークン＝OIDCで確認。合言葉の共有は不要）
//   POST /api/notify       登録者全員にWebプッシュを送る（40件ずつ。cursor を返すので続きを呼ぶ）
//   POST /api/live         「いまの熱さ」を置く（収集プログラムが20秒ごとに呼ぶ）
//
// 環境変数：ALLOW_ORIGIN, ALLOW_REPO（vars）
// シークレット：VAPID_PUBLIC, VAPID_PRIVATE_JWK, STATS_TOKEN, HASH_SALT（初回デプロイ時に自動で作る。STATS_TOKENだけは本人が決める）
//             GH_APP_ID, GH_APP_KEY（任意）：収集プログラムを起こすための GitHub App（組織の App。権限は Actions の読み書きだけ）。
//               実行した人は App の名前で表示され、個人のアカウント名は出ない。GH_APP_KEY は PKCS#8 の秘密鍵（deploy-api が変換して入れる）
//             GH_DISPATCH_TOKEN（任意・予備）：App がないときだけ使う個人のトークン
//
// 定期実行
//   毎日 03:17（日本時間）      古い訪問記録を消す
//   10分おき（GitHub App があるとき）       試合の前後と、1時間ごとに、収集プログラム（midokoro.yml）を起こす。
//                                    GitHub の schedule が動かないことがあるため、こちらから workflow_dispatch で起こす

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

async function gameBump(env, key, kind, n = 1) {
  if (!n) return;
  await env.DB.prepare("INSERT INTO game_events (key, kind, n) VALUES (?1, ?2, ?3) ON CONFLICT(key, kind) DO UPDATE SET n = n + ?3")
    .bind(key, kind, n).run();
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
  const gs = (await env.DB.prepare("SELECT key, date, opponent, peak FROM games ORDER BY date DESC, key DESC LIMIT 60").all()).results;
  const ge = gs.length ? (await env.DB.prepare(`SELECT key, kind, n FROM game_events WHERE key IN (${gs.map(() => "?").join(",")})`)
    .bind(...gs.map((g) => g.key)).all()).results : [];
  const games = gs.map((g) => ({ ...g, sent_full: 0, sent_geki: 0, tap_full: 0, tap_geki: 0, notify_full: 0, notify_geki: 0 }));
  const byKey = Object.fromEntries(games.map((g) => [g.key, g]));
  for (const r of ge) if (byKey[r.key] && r.kind in byKey[r.key]) byKey[r.key][r.kind] = r.n;
  return {
    generated: jst().toISOString().slice(0, 16).replace("T", " "),
    subscribers: Object.values(byDevice).reduce((a, b) => a + b, 0),
    by_device: byDevice,
    totals: Object.fromEntries(total.results.map((r) => [r.kind, r.n])),
    days: Object.values(days),
    games,
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

// ---------- 収集プログラムを起こす（GitHub の schedule の代わり） ----------
const KICK_CRON = "3,13,23,33,43,53 * * * *";
const SITE_STATE = "https://levangamidokoro.github.io/data/state.json";

async function needRun(now) {                // 試合の70分前〜開始3時間後、または1時間以上ページが更新されていないとき
  try {
    const st = await (await fetch(SITE_STATE + "?t=" + now, { cf: { cacheTtl: 0 } })).json();
    const upd = Date.parse((st.updated || "").replace(" ", "T") + ":00+09:00");
    if (!(now - upd < 55 * 60e3)) return true;
    const g = st.today;
    if (g && /^\d{1,2}:\d{2}$/.test(g.start || "") && g.status !== "終了") {
      const start = Date.parse(`${g.date}T${g.start.padStart(5, "0")}:00+09:00`);
      if (now >= start - 70 * 60e3 && now <= start + 3 * 3600e3) return true;
    }
    return false;
  } catch (e) {
    return true;                               // 読めないときは起こしておく
  }
}

const GH = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "midokoro-api" };
let appMemo = { v: null, exp: 0 };

async function appToken(env) {               // GitHub App の鍵から、このリポジトリだけに使える1時間の鍵をもらう
  if (appMemo.v && Date.now() < appMemo.exp) return appMemo.v;
  const der = unb64u(String(env.GH_APP_KEY).replace(/-----[^-]+-----/g, "").replace(/\s+/g, "").replace(/\+/g, "-").replace(/\//g, "_"));
  const key = await crypto.subtle.importKey("pkcs8", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const now = Math.floor(Date.now() / 1000);
  const head = b64u(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
  const claims = b64u(enc.encode(JSON.stringify({ iat: now - 60, exp: now + 540, iss: String(env.GH_APP_ID) })));
  const jwt = `${head}.${claims}.${b64u(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, enc.encode(`${head}.${claims}`)))}`;
  const auth = { ...GH, Authorization: `Bearer ${jwt}` };
  const inst = await fetch(`https://api.github.com/repos/${env.ALLOW_REPO}/installation`, { headers: auth });
  if (!inst.ok) throw new Error(`installation ${inst.status}`);
  const repo = String(env.ALLOW_REPO).split("/")[1];
  const res = await fetch(`https://api.github.com/app/installations/${(await inst.json()).id}/access_tokens`, {
    method: "POST", headers: auth, body: JSON.stringify({ repositories: [repo], permissions: { actions: "write" } }) });
  if (!res.ok) throw new Error(`access_tokens ${res.status}`);
  const t = await res.json();
  appMemo = { v: t.token, exp: Date.parse(t.expires_at) - 5 * 60e3 };
  return t.token;
}

// 実行の依頼：リポジトリの ops/request.json（main）に新しい id が書かれたら、決まったワークフローだけを App の名前で起動する。
// 開発者の push や手動実行で個人のアカウント名が Actions に出ないようにするため
const RUNNABLE = ["midokoro.yml", "deploy-api.yml", "push-test.yml", "live-test.yml", "app-test.yml", "check.yml"];

async function handleRequest(env, hdr) {
  let q;
  try {
    const r = await fetch(`https://raw.githubusercontent.com/${env.ALLOW_REPO}/main/ops/request.json?t=${Date.now()}`, { cf: { cacheTtl: 0 } });
    if (!r.ok) return false;
    q = await r.json();
  } catch (e) { return false; }
  if (!q || !q.id) return false;
  const done = await env.DB.prepare("SELECT v FROM kv WHERE k = 'request'").first("v");
  if (String(q.id) === done) return false;
  await env.DB.prepare("INSERT INTO kv (k, v) VALUES ('request', ?1) ON CONFLICT(k) DO UPDATE SET v = ?1").bind(String(q.id)).run();
  let ran = false;
  for (const job of (Array.isArray(q.run) ? q.run : []).slice(0, 3)) {
    if (!job || !RUNNABLE.includes(job.workflow)) continue;
    const inputs = Object.fromEntries(Object.entries(job.inputs || {}).slice(0, 5).map(([k, v]) => [String(k).slice(0, 40), String(v).slice(0, 200)]));
    const res = await fetch(`https://api.github.com/repos/${env.ALLOW_REPO}/actions/workflows/${job.workflow}/dispatches`,
      { method: "POST", headers: hdr, body: JSON.stringify({ ref: "main", inputs }) });
    await bump(env, res.status === 204 ? "request" : "request_fail");
    if (job.workflow === "midokoro.yml" && res.status === 204) ran = true;
  }
  return ran;
}

async function kick(env) {
  const useApp = !!(env.GH_APP_ID && env.GH_APP_KEY);
  if (!useApp && !env.GH_DISPATCH_TOKEN) return;
  const api = `https://api.github.com/repos/${env.ALLOW_REPO}/actions/workflows/midokoro.yml`;
  try {
    const hdr = { ...GH, Authorization: `Bearer ${useApp ? await appToken(env) : env.GH_DISPATCH_TOKEN}` };
    if (await handleRequest(env, hdr)) return;
    if (!(await needRun(Date.now()))) return;
    for (const status of ["in_progress", "queued"]) {          // もう動いている・待っているなら起こさない
      const r = await fetch(`${api}/runs?status=${status}&per_page=1`, { headers: hdr });
      if (r.ok && (await r.json()).total_count > 0) return;
    }
    const res = await fetch(`${api}/dispatches`, { method: "POST", headers: hdr, body: JSON.stringify({ ref: "main" }) });
    await bump(env, res.status === 204 ? "kick" : "kick_fail");
  } catch (e) {
    await bump(env, "kick_fail");
  }
}

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
  return { key, status: str(r.status, 10), level, meter: int(r.meter, 0, 200), pct: int(r.pct, 0, 300), peak: int(r.peak, 0, 300),
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
      if (url.pathname === "/api/go" && req.method === "GET") {   // 通知のタップ：数えてから公式の試合ページへ（行き先は試合番号から作るので、ほかへは飛ばない）
        const g = url.searchParams.get("g") || "", k = url.searchParams.get("k") === "geki" ? "geki" : "full";
        if (!/^\d{1,10}$/.test(g)) return Response.redirect("https://levangamidokoro.github.io/", 302);
        try {
          const known = await env.DB.prepare("SELECT 1 AS x FROM games WHERE key = ?1").bind(g).first("x");
          if (known) await gameBump(env, g, `tap_${k}`);
        } catch (e) {}
        return Response.redirect(`https://www.bleague.jp/game_detail/?ScheduleKey=${g}&tab=1`, 302);
      }
      if (url.pathname === "/api/stats" && req.method === "GET") {
        if (!authed(req, env.STATS_TOKEN)) return json({ ok: false }, 401, h);
        return json(await stats(env), 200, h);
      }
      if (url.pathname === "/api/notify" && req.method === "POST") {
        if (!(await githubOk(env, req))) return json({ ok: false }, 401, h);
        const r = await body(req);
        const image = /^https:\/\/levangamidokoro\.github\.io\/[\w.-]+\.png$/.test(String(r.image || "")) ? String(r.image) : "";   // 自分のページの画像だけ
        const payload = JSON.stringify({ title: String(r.title || "見どころなう").slice(0, 80), body: String(r.body || "").slice(0, 200), url: String(r.url || "./"), image });
        const game = r.game && /^\d{1,10}$/.test(String(r.game.key || "")) ? r.game : null;   // 試合の通知なら、試合ごとにも数える
        const gk = game ? (r.game.kind === "geki" ? "geki" : "full") : null;
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
        if (game) {
          const pct = Math.max(0, Math.min(300, Math.round(+game.pct || 0)));
          await env.DB.prepare("INSERT INTO games (key, date, opponent, peak) VALUES (?1, ?2, ?3, ?4) ON CONFLICT(key) DO UPDATE SET peak = MAX(peak, ?4), date = ?2, opponent = ?3")
            .bind(String(game.key), String(game.date || "").slice(0, 10), String(game.opponent || "").slice(0, 20), pct).run();
          await gameBump(env, String(game.key), `sent_${gk}`, sent);
          if (cursor === 0) await gameBump(env, String(game.key), `notify_${gk}`);
        }
        const next = rows.length === BATCH ? rows[rows.length - 1].id : null;
        return json({ ok: true, sent, failed, gone: gone.length, cursor: next, ...(env.DEV_NOTIFY_TOKEN ? { why: why.slice(0, 5) } : {}) }, 200, h);
      }
      return json({ ok: false }, 404, h);
    } catch (e) {
      return json({ ok: false }, 500, h);
    }
  },
  async scheduled(ev, env, ctx) {
    if (ev.cron === KICK_CRON) { ctx.waitUntil(kick(env)); return; }
    await purge(env);
  },
};
