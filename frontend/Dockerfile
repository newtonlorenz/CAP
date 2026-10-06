FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
ARG FRONTEND_BASE_PATH=/
ENV VITE_BASE_PATH=$FRONTEND_BASE_PATH
WORKDIR /app
COPY package*.json ./
COPY vendor/ ./vendor/
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine-slim@sha256:32463212baf0e7d91aded2e9b843a4f2b9e017804b8c9d5bae7b51dcef64389c
ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision=$VCS_REF
ARG FRONTEND_BASE_PATH=/
ENV FRONTEND_BASE_PATH=$FRONTEND_BASE_PATH
RUN apk upgrade --no-cache && apk add --no-cache gettext
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html${FRONTEND_BASE_PATH}
COPY start-nginx.sh /start-nginx.sh
RUN chmod +x /start-nginx.sh
ENV API_PROXY_SCHEME=http
ENV API_PROXY_HOSTPORT=backend:8000
ENV API_PROXY_HOST_MODE=preserve
ENV FRONTEND_CLIENT_MAX_BODY_SIZE=2048m
CMD ["/start-nginx.sh"]
