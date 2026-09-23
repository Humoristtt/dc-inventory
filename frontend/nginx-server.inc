
        root /usr/share/nginx/html;
        index index.html;

        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy strict-origin-when-cross-origin always;
        add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'" always;
        add_header Permissions-Policy "camera=(self), microphone=(), geolocation=(), payment=(), usb=()" always;

        location = /healthz {
            access_log off;
            default_type text/plain;
            return 200 "ok\n";
        }

        location /api/ {
            set $backend http://backend:8000;

            limit_req zone=api_per_client burst=60 nodelay;
            limit_req zone=sensitive_per_client burst=5 nodelay;
            limit_req zone=telegram_webhook burst=100 nodelay;

            proxy_pass $backend;
            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Proto $forwarded_proto;

            proxy_connect_timeout 3s;
            proxy_read_timeout 30s;
            proxy_send_timeout 30s;
        }

        location /assets/ {
            try_files $uri =404;
            expires 1y;

            # add_header inheritance stops when a location defines
            # its own add_header directives.
            add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options nosniff always;
            add_header Referrer-Policy strict-origin-when-cross-origin always;
            add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'" always;
            add_header Permissions-Policy "camera=(self), microphone=(), geolocation=(), payment=(), usb=()" always;
            add_header Cache-Control "public, immutable";
        }

        location = /index.html {
            # Keep server security headers alongside the location-specific
            # cache policy; defining add_header here disables inheritance.
            add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options nosniff always;
            add_header Referrer-Policy strict-origin-when-cross-origin always;
            add_header Content-Security-Policy "default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'" always;
            add_header Permissions-Policy "camera=(self), microphone=(), geolocation=(), payment=(), usb=()" always;
            add_header Cache-Control "no-store";
        }

        location / {
            try_files $uri $uri/ /index.html;
        }
