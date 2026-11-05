# Web workspace image. Build context: web/.
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /web
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
USER 10001
EXPOSE 3000
CMD ["node", "server.js"]
