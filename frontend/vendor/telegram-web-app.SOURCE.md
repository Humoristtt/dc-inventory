# Telegram Web App SDK provenance

Vendored runtime asset:

    public/vendor/telegram/telegram-web-app.js

Upstream URL:

    https://telegram.org/js/telegram-web-app.js?63

Retrieved:

    2026-09-02

Upstream response metadata observed during retrieval:

    Last-Modified: Tue, 14 Jul 2026 09:31:36 GMT
    Content-Type: application/javascript
    Content-Length: 116510

Reviewed artifact:

    SHA-256: 3549138a7934039fe7dfd1291a4ee739bd2b705a614308053a8b08a87d85c451
    Size: 116510 bytes

Runtime policy:

- production frontend must load this SDK from the application's own origin;
- production runtime must not depend on telegram.org for SDK delivery;
- updating this file requires an explicit upstream fetch, sanity review,
  new SHA-256, frontend test/build verification and production smoke test.
