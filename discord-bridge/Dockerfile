FROM oven/bun:1-alpine AS install

WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile --production

FROM oven/bun:1-alpine

WORKDIR /app
COPY --from=install /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src

USER bun
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3001/healthz || exit 1

CMD ["bun", "run", "src/index.ts"]
