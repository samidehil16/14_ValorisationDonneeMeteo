FROM node:24-alpine AS build

WORKDIR /app

COPY package*.json .

RUN npm install

COPY . .

RUN npm run build

FROM node:24-alpine AS prod

WORKDIR /app

# Create non-root user
RUN addgroup -S appuser && adduser -S appuser -G appuser

COPY --from=build --chown=appuser:appuser /app/.output /app/.output

ENV NODE_ENV=production
USER appuser

EXPOSE 3000

CMD [ "node", ".output/server/index.mjs" ]
