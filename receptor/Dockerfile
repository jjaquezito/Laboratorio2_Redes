# Receptor — Laboratorio 2 (CC3067 Redes)
# Multi-stage: build del frontend (Node) -> build del backend (Node) -> runtime (Node).

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:22-alpine AS backend-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.build.json ./
COPY src/ ./src/
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=backend-build /app/dist ./dist
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 3000 5001
CMD ["node", "dist/main.js", "--host", "0.0.0.0"]
