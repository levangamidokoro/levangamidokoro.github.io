// Webプッシュ用の鍵（VAPID）と、訪問者を数えるための合言葉を作る。結果は標準出力に JSON で出す（ログには出さないこと）
import { webcrypto as c } from "node:crypto";
const b64u = (b) => Buffer.from(b).toString("base64url");
const k = await c.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const jwk = await c.subtle.exportKey("jwk", k.privateKey);
const pub = new Uint8Array(await c.subtle.exportKey("raw", k.publicKey));
process.stdout.write(JSON.stringify({
  VAPID_PUBLIC: b64u(pub),
  VAPID_PRIVATE_JWK: JSON.stringify({ kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y, d: jwk.d }),
  HASH_SALT: b64u(c.getRandomValues(new Uint8Array(24))),
}));
