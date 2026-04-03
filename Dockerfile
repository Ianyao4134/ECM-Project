# Single-container image: Node gateway + Python Flask backend (Waitress).
# Build: docker build -t ecm-app .
# Run:  docker run --rm -p 8080:8080 -e DEEPSEEK_API_KEY=sk-... ecm-app

FROM node:22-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    pkg-config \
    libfreetype6-dev \
    libpng-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages --upgrade pip setuptools wheel \
  && pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

ENV NODE_ENV=production
ENV PORT=8080
ENV HOST=0.0.0.0
ENV ECM_BACKEND_URL=http://127.0.0.1:9000

EXPOSE 8080

CMD ["sh", "-c", "waitress-serve --listen=127.0.0.1:9000 app.main:app & exec node server/prod.js"]
