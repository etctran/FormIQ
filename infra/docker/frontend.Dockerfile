FROM node:20-slim AS builder

WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /src/dist /usr/share/nginx/html
EXPOSE 80
