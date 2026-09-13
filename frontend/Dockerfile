# Frontend image: build the Vite app, serve with nginx; /api and /metrics
# proxy to the backend service.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Run the nginx MASTER as the unprivileged `nginx` account the image already
# ships (stock nginx only drops the WORKERS to it; the master stays root).
# Two things have to be true for that to work:
#   1. the listener is 8080, not 80 — a non-root process cannot bind a port
#      below 1024 and a container's default capability set is not granted to
#      non-root processes. The PUBLISHED port is unchanged: docker-compose.yml
#      maps ${FRONTEND_PORT:-5173} to 8080 now instead of 80.
#   2. the pid file and the temp/cache trees are writable by that account.
#      /var/run is root-owned, so the pid file is pre-created and chowned —
#      nginx truncates an existing file rather than creating one.
# /etc/nginx/nginx.conf still carries `user nginx;`; a non-root master logs
# one "ignored" warning for it at startup and continues, which is expected.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html /etc/nginx/conf.d

USER nginx
EXPOSE 8080
