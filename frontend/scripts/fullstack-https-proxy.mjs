import {
  readFileSync,
} from "node:fs";
import http from "node:http";
import https from "node:https";

const listenHost =
  process.env.FULLSTACK_HTTPS_HOST?.trim()
  || "127.0.0.1";
const listenPort = Number(
  process.env.FULLSTACK_HTTPS_PORT ?? "8443",
);
const upstreamHost =
  process.env.FULLSTACK_UPSTREAM_HOST?.trim()
  || "127.0.0.1";
const upstreamPort = Number(
  process.env.FULLSTACK_UPSTREAM_PORT ?? "8080",
);
const keyPath =
  process.env.FULLSTACK_HTTPS_KEY?.trim();
const certPath =
  process.env.FULLSTACK_HTTPS_CERT?.trim();

if (!keyPath || !certPath) {
  throw new Error(
    "FULLSTACK_HTTPS_KEY and FULLSTACK_HTTPS_CERT are required",
  );
}
if (
  !Number.isInteger(listenPort)
  || listenPort < 1
  || listenPort > 65_535
  || !Number.isInteger(upstreamPort)
  || upstreamPort < 1
  || upstreamPort > 65_535
) {
  throw new Error("invalid HTTPS proxy port");
}

const server = https.createServer(
  {
    key: readFileSync(keyPath),
    cert: readFileSync(certPath),
  },
  (request, response) => {
    const upstream = http.request(
      {
        host: upstreamHost,
        port: upstreamPort,
        method: request.method,
        path: request.url,
        headers: request.headers,
      },
      (upstreamResponse) => {
        response.writeHead(
          upstreamResponse.statusCode ?? 502,
          upstreamResponse.headers,
        );
        upstreamResponse.pipe(response);
      },
    );

    upstream.on("error", (error) => {
      if (!response.headersSent) {
        response.writeHead(
          502,
          {
            "Content-Type": "text/plain; charset=utf-8",
          },
        );
      }
      response.end(
        `upstream unavailable: ${error.message}\n`,
      );
    });

    request.pipe(upstream);
  },
);

server.listen(
  listenPort,
  listenHost,
  () => {
    process.stdout.write(
      `FULLSTACK_HTTPS_PROXY=https://localhost:${listenPort}\n`,
    );
  },
);

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
