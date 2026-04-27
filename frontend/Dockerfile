# syntax=docker/dockerfile:1.7
# ── Build stage (Docker Hardened Image, dev variant) ──────────────────
FROM dhi.io/node:24-debian13-dev AS build

WORKDIR /app

ENV NPM_CONFIG_CACHE=/root/.npm

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ── Runtime stage (DHI distroless: no shell, no npm, non-root) ────────
FROM dhi.io/node:24-debian13

WORKDIR /app

COPY --from=build --chown=nonroot:nonroot /app/.output /app/.output

ENV NODE_ENV=production

EXPOSE 3000
ENTRYPOINT ["node", ".output/server/index.mjs"]
