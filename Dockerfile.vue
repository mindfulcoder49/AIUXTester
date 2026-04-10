FROM node:20-bookworm-slim AS vue-build

WORKDIR /build/frontend-vue

COPY frontend-vue/package.json frontend-vue/package-lock.json ./
RUN npm ci

COPY frontend-vue/ ./
RUN npm run build


FROM mcr.microsoft.com/playwright/python:v1.41.2-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    UI_VARIANT=vue

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
COPY --from=vue-build /build/frontend-vue/dist /app/frontend-vue/dist

EXPOSE 8080

CMD ["bash", "-lc", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
