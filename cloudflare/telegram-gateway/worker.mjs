const ALLOWED_METHODS = new Set([
  "sendMessage",
  "sendPhoto",
  "deleteMessage",
  "editMessageText",
  "editMessageReplyMarkup",
  "answerCallbackQuery",
]);

export const MAX_BODY_BYTES = 64 * 1024;

const SECRET_HEADER = "X-DC-Inventory-Gateway-Secret";

async function digest(value) {
  return new Uint8Array(
    await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(value),
    ),
  );
}

async function secretsEqual(left, right) {
  const [a, b] = await Promise.all([
    digest(left),
    digest(right),
  ]);

  let difference = a.length ^ b.length;
  const length = Math.max(a.length, b.length);

  for (let index = 0; index < length; index += 1) {
    difference |=
      (a[index] ?? 0) ^ (b[index] ?? 0);
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

export async function readBodyLimited(
  request,
  maxBytes = MAX_BODY_BYTES,
) {
  const contentLengthRaw =
    request.headers.get("content-length");

  if (contentLengthRaw !== null) {
    const contentLength = Number(
      contentLengthRaw,
    );

    if (
      Number.isFinite(contentLength)
      && contentLength > maxBytes
    ) {
      return {
        status: 413,
        text: null,
      };
    }
  }

  if (request.body === null) {
    return {
      status: 200,
      text: "",
    };
  }

  const reader = request.body.getReader();
  const chunks = [];
  let totalBytes = 0;

  try {
    while (true) {
      const { done, value } =
        await reader.read();

      if (done) {
        break;
      }

      const chunk =
        value instanceof Uint8Array
          ? value
          : new Uint8Array(value);

      totalBytes += chunk.byteLength;

      if (totalBytes > maxBytes) {
        try {
          await reader.cancel(
            "gateway request body too large",
          );
        } catch {
          void 0;
        }

        return {
          status: 413,
          text: null,
        };
      }

      chunks.push(chunk);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;

  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    return {
      status: 200,
      text: new TextDecoder(
        "utf-8",
        { fatal: true },
      ).decode(body),
    };
  } catch {
    return {
      status: 400,
      text: null,
    };
  }
}

export default {
  async fetch(request, env) {
    if (
      !env.BOT_TOKEN
      || !env.GATEWAY_SECRET
    ) {
      return jsonResponse(
        { ok: false },
        503,
      );
    }

    if (request.method !== "POST") {
      return jsonResponse(
        { ok: false },
        405,
      );
    }

    const url = new URL(request.url);
    const match =
      /^\/telegram\/([A-Za-z]+)$/.exec(
        url.pathname,
      );

    if (
      !match
      || !ALLOWED_METHODS.has(match[1])
    ) {
      return jsonResponse(
        { ok: false },
        404,
      );
    }

    const provided =
      request.headers.get(SECRET_HEADER)
      ?? "";

    if (
      !(await secretsEqual(
        provided,
        env.GATEWAY_SECRET,
      ))
    ) {
      return jsonResponse(
        { ok: false },
        401,
      );
    }

    const bodyResult =
      await readBodyLimited(request);

    if (bodyResult.status !== 200) {
      return jsonResponse(
        { ok: false },
        bodyResult.status,
      );
    }

    let payload;

    try {
      payload = JSON.parse(
        bodyResult.text,
      );
    } catch {
      return jsonResponse(
        { ok: false },
        400,
      );
    }

    if (
      payload === null
      || Array.isArray(payload)
      || typeof payload !== "object"
    ) {
      return jsonResponse(
        { ok: false },
        400,
      );
    }

    const method = match[1];
    let upstream;

    try {
      upstream = await fetch(
        `https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify(payload),
        },
      );
    } catch {
      return jsonResponse(
        { ok: false },
        502,
      );
    }

    return new Response(
      await upstream.text(),
      {
        status: upstream.status,
        headers: {
          "Content-Type":
            "application/json",
          "Cache-Control": "no-store",
        },
      },
    );
  },
};
