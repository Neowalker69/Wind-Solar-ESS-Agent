FROM node:22-alpine AS build

WORKDIR /workspace

COPY apps/harness-control/package.json apps/harness-control/package-lock.json ./apps/harness-control/
WORKDIR /workspace/apps/harness-control
RUN npm ci

WORKDIR /workspace
COPY frontend/src ./frontend/src
COPY frontend/public ./apps/harness-control/public
COPY apps/harness-control ./apps/harness-control
COPY proto ./proto

WORKDIR /workspace/apps/harness-control
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
