import assert from "node:assert/strict";
import test from "node:test";

import worker from "./worker.mjs";

const env = {
  BOT_TOKEN: "123456:test-token",
  GATEWAY_SECRET: "gateway-secret-value",
};

function makeRequest(path, secret = env.GATEWAY_SECRET, body = {}) {
  return new Request(`https://gateway.example${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-DC-Inventory-Gateway-Secret": secret,
    },
    body: JSON.stringify(body),
  });
}

test("rejects wrong gateway secret", async () => {
  const response = await worker.fetch(
    makeRequest("/telegram/sendMessage", "wrong-secret"),
    env,
  );
  assert.equal(response.status, 401);
});

test("rejects methods outside allowlist", async () => {
  const response = await worker.fetch(
    makeRequest("/telegram/deleteWebhook"),
    env,
  );
  assert.equal(response.status, 404);
});

test("forwards allowed Telegram method", async () => {
  const originalFetch = globalThis.fetch;
  let upstreamUrl = "";
  globalThis.fetch = async (url) => {
    upstreamUrl = String(url);
    return new Response(JSON.stringify({ ok: true, result: {} }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const response = await worker.fetch(
      makeRequest("/telegram/sendMessage", env.GATEWAY_SECRET, {
        chat_id: 42,
        text: "hello",
      }),
      env,
    );
    assert.equal(response.status, 200);
    assert.equal((await response.json()).ok, true);
    assert.equal(
      upstreamUrl,
      `https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage`,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("forwards start cleanup and reaction methods", async () => {
  const originalFetch = globalThis.fetch;
  const upstreamUrls = [];
  globalThis.fetch = async (url) => {
    upstreamUrls.push(String(url));
    return new Response(JSON.stringify({ ok: true, result: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    for (const method of ["deleteMessage", "setMessageReaction"]) {
      const response = await worker.fetch(
        makeRequest(`/telegram/${method}`, env.GATEWAY_SECRET, {
          chat_id: 42,
          message_id: 7,
        }),
        env,
      );
      assert.equal(response.status, 200);
      assert.equal((await response.json()).ok, true);
    }

    assert.deepEqual(upstreamUrls, [
      `https://api.telegram.org/bot${env.BOT_TOKEN}/deleteMessage`,
      `https://api.telegram.org/bot${env.BOT_TOKEN}/setMessageReaction`,
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
