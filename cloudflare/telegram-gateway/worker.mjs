const ALLOWED_METHODS = new Set([
  "sendMessage",
  "deleteMessage",
  "editMessageText",
  "editMessageReplyMarkup",
  "answerCallbackQuery",
]);

const MAX_BODY_BYTES = 64 * 1024;
const SECRET_HEADER = "X-DC-Inventory-Gateway-Secret";

async function digest(value) {
  return new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
  );
}

async function secretsEqual(left, right) {
  const [a, b] = await Promise.all([digest(left), digest(right)]);
  let difference = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return difference === 0;
}

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export default {
  async fetch(request, env) {
    if (!env.BOT_TOKEN || !env.GATEWAY_SECRET) {
      return jsonResponse({ ok: false }, 503);
    }
    if (request.method !== "POST") {
      return jsonResponse({ ok: false }, 405);
    }

    const url = new URL(request.url);
    const match = /^\/telegram\/([A-Za-z]+)$/.exec(url.pathname);
    if (!match || !ALLOWED_METHODS.has(match[1])) {
      return jsonResponse({ ok: false }, 404);
    }

    const provided = request.headers.get(SECRET_HEADER) ?? "";
    if (!(await secretsEqual(provided, env.GATEWAY_SECRET))) {
      return jsonResponse({ ok: false }, 401);
    }

    const raw = await request.text();
    if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) {
      return jsonResponse({ ok: false }, 413);
    }

    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return jsonResponse({ ok: false }, 400);
    }
    if (payload === null || Array.isArray(payload) || typeof payload !== "object") {
      return jsonResponse({ ok: false }, 400);
    }

    const method = match[1];
    let upstream;
    try {
      upstream = await fetch(
        `https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
    } catch {
      return jsonResponse({ ok: false }, 502);
    }

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  },
};
