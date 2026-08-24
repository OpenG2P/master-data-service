# Master Data UI — Next.js standalone image.
#
# Built with docker context = master-data-ui (see .gitlab-ci.yml). Published as
# registry.gitlab.com/openg2p/platform-services/master-data-service/master-data-ui.
FROM node:20-alpine AS base
WORKDIR /app

FROM base AS builder
# Install dependencies first so this layer is cached unless the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci
# Then copy the rest of the source and produce the standalone build
# (next.config.ts sets `output: "standalone"`).
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM base AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Standalone output already includes a fully traced node_modules
# (sharp + its native libvips binary included) — no separate
# `npm install sharp` or post-hoc `chown -R` needed. Ownership is
# set inline via --chown at copy time instead.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
