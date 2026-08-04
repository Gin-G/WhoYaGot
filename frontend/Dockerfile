# ── Build ────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# No VITE_API_URL here on purpose: the API URL is resolved at runtime from
# config.js, so this image is not tied to one environment.
RUN npm run build

# ── Serve ────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/40-whoyagot-config.sh /docker-entrypoint.d/40-whoyagot-config.sh
RUN chmod +x /docker-entrypoint.d/40-whoyagot-config.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/healthz || exit 1
