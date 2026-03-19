FROM golang:1.24-bookworm AS wgcf-builder

WORKDIR /build
RUN git clone --depth 1 --branch v2.2.30 https://github.com/ViRb3/wgcf.git .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=$(go env GOARCH) go build -o /out/wgcf .

FROM golang:1.26-bookworm AS wireproxy-builder

WORKDIR /build
RUN git clone --depth 1 --branch v1.1.2 https://github.com/octeep/wireproxy.git .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=$(go env GOARCH) go build -o /out/wireproxy ./cmd/wireproxy

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    USE_XVFB=1 \
    WARP_ENABLED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    fonts-noto-cjk \
    fonts-liberation \
    ca-certificates \
    curl \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc-s1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wgcf-builder /out/wgcf /usr/local/bin/wgcf
COPY --from=wireproxy-builder /out/wireproxy /usr/local/bin/wireproxy

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    mkdir -p /app/logs /app/sso /app/warp

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "DrissionPage_example.py"]
