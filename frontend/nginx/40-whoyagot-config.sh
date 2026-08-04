#!/bin/sh
# Runs before nginx starts (the nginx image executes /docker-entrypoint.d/*.sh).
#
# Points the proxy at the API and writes the browser-facing config, so the same
# image serves every environment without a rebuild.
set -eu

: "${API_UPSTREAM:=http://whoyagot-api:8000}"
: "${PUBLIC_API_URL:=/api}"
: "${GOOGLE_CLIENT_ID:=}"

# Trailing slashes here would produce a double slash in proxy_pass.
API_UPSTREAM=$(printf '%s' "$API_UPSTREAM" | sed 's|/*$||')

sed -i "s|__API_UPSTREAM__|${API_UPSTREAM}|g" /etc/nginx/conf.d/default.conf

cat > /usr/share/nginx/html/config.js <<EOF
window.__WHOYAGOT__ = {
  apiUrl: "${PUBLIC_API_URL}",
  googleClientId: "${GOOGLE_CLIENT_ID}"
};
EOF

echo "whoyagot-web: proxying /api -> ${API_UPSTREAM}, browser apiUrl=${PUBLIC_API_URL}"
