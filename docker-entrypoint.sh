#!/bin/sh
set -eu

WARP_ENABLED="${WARP_ENABLED:-1}"
WARP_DIR="${WARP_DIR:-/app/warp}"
WARP_PROXY_HOST="${WARP_PROXY_HOST:-127.0.0.1}"
WARP_HTTP_PORT="${WARP_HTTP_PORT:-8787}"
WARP_SOCKS5_PORT="${WARP_SOCKS5_PORT:-8788}"
WARP_HEALTH_PORT="${WARP_HEALTH_PORT:-8789}"
WARP_DEVICE_NAME="${WARP_DEVICE_NAME:-grok-register-docker}"
WARP_DEVICE_MODEL="${WARP_DEVICE_MODEL:-PC}"
WARP_ACCOUNT_FILE="${WARP_DIR}/wgcf-account.toml"
WARP_PROFILE_FILE="${WARP_DIR}/wgcf-profile.conf"
WARP_WIREPROXY_FILE="${WARP_DIR}/wireproxy.conf"
WARP_HTTP_PROXY="http://${WARP_PROXY_HOST}:${WARP_HTTP_PORT}"
WARP_SOCKS_PROXY="socks5://${WARP_PROXY_HOST}:${WARP_SOCKS5_PORT}"

mkdir -p "${WARP_DIR}" /app/logs /app/sso

generate_warp_profile() {
    if [ -f "${WARP_ACCOUNT_FILE}" ] && [ -f "${WARP_PROFILE_FILE}" ]; then
        echo "[*] Reusing existing WARP profile from ${WARP_DIR}"
        return
    fi

    (
        cd "${WARP_DIR}"
        if [ ! -f wgcf-account.toml ]; then
            echo "[*] Registering a new Cloudflare WARP device in ${WARP_DIR}"
            rm -f wgcf-account.toml wgcf-profile.conf
            wgcf register --accept-tos --name "${WARP_DEVICE_NAME}" --model "${WARP_DEVICE_MODEL}"
        else
            echo "[*] Reusing existing WARP account in ${WARP_DIR}"
        fi
        if [ -n "${WARP_LICENSE_KEY:-}" ]; then
            wgcf update --license-key "${WARP_LICENSE_KEY}"
        fi
        wgcf generate
    )
}

write_wireproxy_config() {
    cat > "${WARP_WIREPROXY_FILE}" <<EOF
WGConfig = ${WARP_PROFILE_FILE}

[Socks5]
BindAddress = ${WARP_PROXY_HOST}:${WARP_SOCKS5_PORT}

[http]
BindAddress = ${WARP_PROXY_HOST}:${WARP_HTTP_PORT}
EOF
}

start_warp_proxy() {
    echo "[*] Starting wireproxy via ${WARP_WIREPROXY_FILE}"
    wireproxy -c "${WARP_WIREPROXY_FILE}" -i "${WARP_PROXY_HOST}:${WARP_HEALTH_PORT}" >/app/logs/wireproxy.log 2>&1 &
    WIREPROXY_PID=$!

    i=0
    while [ "$i" -lt 30 ]; do
        if curl -fsS "http://${WARP_PROXY_HOST}:${WARP_HEALTH_PORT}/readyz" >/dev/null 2>&1; then
            echo "[*] WARP proxy is ready: ${WARP_HTTP_PROXY}"
            return
        fi
        i=$((i + 1))
        sleep 1
    done

    echo "[Warn] WARP proxy health check did not become ready in time, recent logs:"
    tail -n 50 /app/logs/wireproxy.log || true
    kill "${WIREPROXY_PID}" >/dev/null 2>&1 || true
    exit 1
}

if [ "${WARP_ENABLED}" = "1" ]; then
    generate_warp_profile
    write_wireproxy_config
    start_warp_proxy

    export GROK_REGISTER_PROXY="${GROK_REGISTER_PROXY:-${WARP_HTTP_PROXY}}"
    export GROK_REGISTER_BROWSER_PROXY="${GROK_REGISTER_BROWSER_PROXY:-${WARP_HTTP_PROXY}}"
    export HTTP_PROXY="${HTTP_PROXY:-${WARP_HTTP_PROXY}}"
    export HTTPS_PROXY="${HTTPS_PROXY:-${WARP_HTTP_PROXY}}"
    export ALL_PROXY="${ALL_PROXY:-${WARP_SOCKS_PROXY}}"
    export http_proxy="${http_proxy:-${HTTP_PROXY}}"
    export https_proxy="${https_proxy:-${HTTPS_PROXY}}"
    export all_proxy="${all_proxy:-${ALL_PROXY}}"
fi

exec "$@"
