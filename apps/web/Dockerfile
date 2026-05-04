FROM node:20-alpine AS deps
RUN apk add --no-cache ca-certificates libc6-compat
WORKDIR /app

COPY package.json ./

ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
ARG NPM_STRICT_SSL=true
ENV NPM_CONFIG_REGISTRY=${NPM_CONFIG_REGISTRY}

RUN npm config set registry "${NPM_CONFIG_REGISTRY}" \
    && npm config set fetch-retries 10 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && if [ "${NPM_STRICT_SSL}" = "false" ]; then npm config set strict-ssl false; fi \
    && npm install

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
