# Frontend image: build the Vite app, serve with nginx; /api and /metrics
# proxy to the backend service.
FROM node:22-slim AS build
WORKDIR /app

# Optional build-time CA — see backend/Dockerfile for the rationale. No-op
# without the secret; node ships its own root bundle, so it is pointed at
# the system store explicitly.
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
RUN --mount=type=secret,id=proxy_ca,target=/tmp/proxy-ca.crt \
    if [ -s /tmp/proxy-ca.crt ]; then \
      apt-get update \
      && apt-get install -y --no-install-recommends ca-certificates \
      && mkdir -p /usr/local/share/ca-certificates \
      && cp /tmp/proxy-ca.crt /usr/local/share/ca-certificates/proxy-ca.crt \
      && update-ca-certificates \
      && rm -rf /var/lib/apt/lists/*; \
    fi

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
