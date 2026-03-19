# Grok 账号批量注册工具

基于 [DrissionPage](https://github.com/g1879/DrissionPage) 的 Grok (x.ai) 账号自动注册脚本，支持通过 [DuckMail](https://duckmail.sbs) 或 [temp-mail-api](https://temp-mail-api.deno.dev/docs) 临时邮箱接收验证码，并通过 Chrome 扩展修复 CDP `MouseEvent.screenX/screenY` 缺陷绕过 Cloudflare Turnstile。

注册完成后自动推送 SSO token 到 [grok2api](https://github.com/chenyme/grok2api) 号池。

## 特性

- 支持 DuckMail 与 temp-mail-api 两种临时邮箱服务
- DuckMail 临时邮箱（`curl_cffi` TLS 指纹伪装）
- Cloudflare Turnstile 自动绕过（Chrome 扩展 patch `MouseEvent.screenX/screenY`）
- 无头服务器支持（Xvfb 虚拟显示器，自动检测 Linux 环境）
- 中英文界面自动适配
- 自动推送 SSO token 到 grok2api（支持 append 合并模式）

---

## 环境要求

- Python 3.10+
- Chromium 或 Chrome 浏览器
- 二选一：
- [DuckMail](https://duckmail.sbs) 账号（用于创建临时邮箱）
- [temp-mail-api](https://temp-mail-api.deno.dev/docs) 的 API Key
- 可选：[grok2api](https://github.com/chenyme/grok2api) 实例（用于自动导入 SSO token）

---

## 安装

```bash
pip install -r requirements.txt
```

无头服务器（Linux）额外安装：

```bash
apt install -y xvfb
pip install PyVirtualDisplay
# 推荐用 playwright 装 chromium（避免 snap 版 AppArmor 限制）
pip install playwright && python -m playwright install chromium && python -m playwright install-deps chromium
```

---

## WebUI

项目现在包含一个带登录鉴权的 WebUI 面板，可用于：

- 输入注册数量并启动任务
- 查看当前运行状态
- 查看最新运行日志
- 查看 SSO 文件列表
- 一键复制当前 SSO 内容

启动方式：

```bash
python webui.py
```

默认访问地址：

```text
http://127.0.0.1:8780
```

默认登录配置来自 `config.json`：

```json
{
  "webui": {
    "host": "127.0.0.1",
    "port": 8780,
    "username": "admin",
    "password": "change_me",
    "secret_key": "change_this_webui_secret"
  }
}
```

建议首次使用就修改：

- `webui.username`
- `webui.password`
- `webui.secret_key`

如果在 Docker 中运行 WebUI，可以直接覆盖启动命令并映射端口：

```bash
docker run --rm \
  -p 8780:8780 \
  -e GROK_REGISTER_WEBUI_USERNAME=admin \
  -e GROK_REGISTER_WEBUI_PASSWORD=change_me \
  -e GROK_REGISTER_WEBUI_SECRET_KEY=replace_me \
  -v $(pwd)/warp:/app/warp \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/sso:/app/sso \
  grok-register \
  python webui.py
```

Docker 镜像内默认会把 `GROK_REGISTER_WEBUI_HOST` 设为 `0.0.0.0`，这样映射端口后可直接从宿主机访问；本地直接运行 `python webui.py` 时默认仍是 `127.0.0.1`。

---

## Docker

项目现在包含可直接打包的 Dockerfile，已覆盖 Linux 运行依赖：

- Python 3.12
- Chromium
- Xvfb
- `PyVirtualDisplay`
- `wgcf`（启动时生成 Cloudflare WARP WireGuard 配置）
- `wireproxy`（用户态 WireGuard 代理）
- 常用系统库与中文字体

构建镜像：

```bash
docker build -t grok-register .
```

推荐通过环境变量传配置运行：

```bash
docker run --rm \
  -e GROK_REGISTER_EMAIL_PROVIDER=temp-mail-api \
  -e GROK_REGISTER_TEMP_MAIL_API_KEY=your_api_key \
  -e GROK_REGISTER_RUN_COUNT=1 \
  -v $(pwd)/warp:/app/warp \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/sso:/app/sso \
  grok-register
```

如果你仍想用 `config.json`，也可以自行挂载到容器内的 `/app/config.json`。

### Docker 内置 WARP

容器入口会默认执行以下动作：

- 在 `/app/warp` 下自动生成或复用 `wgcf-account.toml`
- 自动生成 `wgcf-profile.conf`
- 自动生成 `wireproxy.conf`
- 启动用户态的 WARP HTTP/SOCKS5 代理
- 默认把项目内的 `proxy`、`browser_proxy` 以及容器内常见代理环境变量指向这个 WARP 代理

也就是说，默认后续邮箱请求和浏览器流量都会走 WARP。

推荐把 `/app/warp` 挂载出来，这样容器重启后会复用同一个 WARP 账户，而不是每次重新注册：

```bash
-v $(pwd)/warp:/app/warp
```

可用环境变量：

| 环境变量 | 默认值 | 说明 |
|------|------|------|
| `WARP_ENABLED` | `1` | 是否启用容器内置 WARP 代理 |
| `WARP_DIR` | `/app/warp` | WARP 账户与配置文件目录 |
| `WARP_DEVICE_NAME` | `grok-register-docker` | `wgcf register` 使用的设备名 |
| `WARP_DEVICE_MODEL` | `PC` | `wgcf register` 使用的设备型号 |
| `WARP_LICENSE_KEY` | 空 | 可选，若提供则会在启动时绑定到 Warp+ |
| `WARP_PROXY_HOST` | `127.0.0.1` | 本地代理监听地址 |
| `WARP_HTTP_PORT` | `8787` | wireproxy HTTP 代理端口 |
| `WARP_SOCKS5_PORT` | `8788` | wireproxy SOCKS5 代理端口 |
| `WARP_HEALTH_PORT` | `8789` | wireproxy 健康检查端口 |

如果你不想默认走 WARP，可以设置：

```bash
-e WARP_ENABLED=0
```

### GHCR 自动发布

仓库已包含 GitHub Actions 工作流：

- 文件：`.github/workflows/docker-publish.yml`
- 推送到 `main` / `master` 时自动构建并推送到 `ghcr.io`
- 推送 `v*` tag 时自动构建并推送 tag 镜像
- Pull Request 时只构建，不推送
- 支持手动触发 `workflow_dispatch`

镜像地址格式：

```text
ghcr.io/<owner>/<repo>
```

例如当前仓库默认会发布到：

```text
ghcr.io/alice-qwq77/grok-register
```

常见标签包括：

- 分支名
- Git tag
- commit sha
- 默认分支额外附带 `latest`

---

## 配置文件（config.json）

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
    "run": { "count": 10, "restart_browser_every_round": true },
    "email_provider": "duckmail",
    "duckmail_api_base": "https://api.duckmail.sbs",
    "duckmail_bearer": "<your_duckmail_bearer_token>",
    "temp_mail_api_base": "https://temp-mail-api.deno.dev",
    "temp_mail_api_key": "<your_temp_mail_api_key>",
    "temp_mail_provider": "",
    "temp_mail_domain": "",
    "temp_mail_prefix": "",
    "proxy": "",
    "browser_proxy": "",
    "api": {
        "endpoint": "",
        "token": "",
        "append": true
    }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `run.count` | int | 注册轮数，`0` 为无限循环，可通过 `--count` 覆盖 |
| `run.restart_browser_every_round` | bool | 每轮结束后是否完整重启浏览器，默认 `true`，低配服务器更稳定 |
| `email_provider` | string | 邮箱服务提供方，可选 `duckmail` 或 `temp-mail-api` |
| `duckmail_api_base` | string | DuckMail API 地址，默认 `https://api.duckmail.sbs` |
| `duckmail_bearer` | string | DuckMail Bearer Token（[获取方式](#获取-duckmail-bearer-token)） |
| `temp_mail_api_base` | string | temp-mail-api 网关地址，默认 `https://temp-mail-api.deno.dev`，也可改成你自己的自部署地址 |
| `temp_mail_api_key` | string | temp-mail-api 的 API Key |
| `temp_mail_provider` | string | 指定 temp-mail-api 的 provider 名称（可选） |
| `temp_mail_domain` | string | 指定 temp-mail-api 生成邮箱时使用的域名（可选） |
| `temp_mail_prefix` | string | 指定 temp-mail-api 生成邮箱时使用的前缀（可选） |
| `proxy` | string | 邮箱 API 请求代理（可选） |
| `browser_proxy` | string | 浏览器代理，无头服务器需翻墙时填写（可选） |
| `webui.host` | string | WebUI 监听地址，默认 `127.0.0.1` |
| `webui.port` | int | WebUI 监听端口，默认 `8780` |
| `webui.username` | string | WebUI 登录用户名 |
| `webui.password` | string | WebUI 登录密码 |
| `webui.secret_key` | string | WebUI 会话密钥 |
| `api.endpoint` | string | grok2api 管理接口地址，留空跳过推送 |
| `api.token` | string | grok2api 的 `app_key` |
| `api.append` | bool | `true` 合并线上已有 token，`false` 覆盖 |

---

## 环境变量

现在项目支持通过环境变量传入配置，且优先级高于 `config.json`。

支持的环境变量如下：

| 环境变量 | 对应配置项 |
|------|------|
| `GROK_REGISTER_RUN_COUNT` | `run.count` |
| `GROK_REGISTER_RESTART_BROWSER_EVERY_ROUND` | `run.restart_browser_every_round` |
| `GROK_REGISTER_EMAIL_PROVIDER` | `email_provider` |
| `GROK_REGISTER_DUCKMAIL_API_BASE` | `duckmail_api_base` |
| `GROK_REGISTER_DUCKMAIL_BEARER` | `duckmail_bearer` |
| `GROK_REGISTER_TEMP_MAIL_API_BASE` | `temp_mail_api_base` |
| `GROK_REGISTER_TEMP_MAIL_API_KEY` | `temp_mail_api_key` |
| `GROK_REGISTER_TEMP_MAIL_PROVIDER` | `temp_mail_provider` |
| `GROK_REGISTER_TEMP_MAIL_DOMAIN` | `temp_mail_domain` |
| `GROK_REGISTER_TEMP_MAIL_PREFIX` | `temp_mail_prefix` |
| `GROK_REGISTER_PROXY` | `proxy` |
| `GROK_REGISTER_BROWSER_PROXY` | `browser_proxy` |
| `GROK_REGISTER_WEBUI_HOST` | `webui.host` |
| `GROK_REGISTER_WEBUI_PORT` | `webui.port` |
| `GROK_REGISTER_WEBUI_USERNAME` | `webui.username` |
| `GROK_REGISTER_WEBUI_PASSWORD` | `webui.password` |
| `GROK_REGISTER_WEBUI_SECRET_KEY` | `webui.secret_key` |
| `GROK_REGISTER_API_ENDPOINT` | `api.endpoint` |
| `GROK_REGISTER_API_TOKEN` | `api.token` |
| `GROK_REGISTER_API_APPEND` | `api.append` |

示例：

```powershell
$env:GROK_REGISTER_EMAIL_PROVIDER="temp-mail-api"
$env:GROK_REGISTER_TEMP_MAIL_API_KEY="your_api_key"
$env:GROK_REGISTER_RUN_COUNT="5"
python DrissionPage_example.py
```

`GROK_REGISTER_API_APPEND` 支持的真值有：`1`、`true`、`yes`、`on`。

---

## 使用 temp-mail-api

如果你要切换到新的邮箱服务，可以在 `config.json` 中这样配置：

```json
{
    "email_provider": "temp-mail-api",
    "temp_mail_api_base": "https://temp-mail-api.deno.dev",
    "temp_mail_api_key": "<your_temp_mail_api_key>",
    "temp_mail_provider": "",
    "temp_mail_domain": "",
    "temp_mail_prefix": ""
}
```

说明：

- `temp_mail_api_key` 为必填，接口使用 `Authorization: Bearer <api-key>` 鉴权
- `temp_mail_api_base` 默认值是公开演示地址 `https://temp-mail-api.deno.dev`
- `temp_mail_provider`、`temp_mail_domain`、`temp_mail_prefix` 都是可选项，不填时走服务端默认路由
- 当前脚本已接入 `GET/POST /api/generate-email`、`GET /api/emails`、`GET /api/email/:id` 这几个收码所需接口
- 如果同时设置了环境变量，则环境变量会覆盖 `config.json` 中的值
- 如果你的 temp-mail-api 部署在别的域名或端口，可以通过 `temp_mail_api_base` 或环境变量 `GROK_REGISTER_TEMP_MAIL_API_BASE` 覆盖

---

## 获取 DuckMail Bearer Token

1. 打开 [duckmail.sbs](https://duckmail.sbs) 并注册登录
2. 打开浏览器开发者工具 (F12) → Network
3. 刷新页面，找到任意发往 `api.duckmail.sbs` 的请求
4. 复制请求头中 `Authorization: Bearer <token>` 里的 token
5. 填入 `config.json` 的 `duckmail_bearer` 字段

---

## 启动方式

```bash
# 按 config.json 中 run.count 执行（默认 10 轮）
python DrissionPage_example.py

# 指定轮数
python DrissionPage_example.py --count 50

# 无限循环
python DrissionPage_example.py --count 0
```

无头服务器会自动启用 Xvfb，无需额外配置。

---

## 输出文件

```
sso/
  sso_<timestamp>.txt     ← 每行一个 SSO token
logs/
  run_<timestamp>.log     ← 每轮注册的邮箱、密码和结果
```

目录在首次运行时自动创建。

---

## 文件结构

```
├── DrissionPage_example.py     # 主脚本
├── email_register.py           # 临时邮箱封装（DuckMail / temp-mail-api）
├── config.json                 # 配置文件（不入库）
├── config.example.json         # 配置模板
├── requirements.txt            # Python 依赖
├── turnstilePatch/             # Chrome 扩展（Turnstile patch）
│   ├── manifest.json
│   └── script.js
├── sso/                        # SSO token 输出（自动创建）
└── logs/                       # 运行日志（自动创建）
```

---

## 无头服务器部署注意

- snap 版 chromium 在 root 下有 AppArmor 限制，推荐用 playwright 安装的 chromium
- 服务器直连 x.ai 可能被墙，需在 `browser_proxy` 填写代理地址
- 脚本自动检测 Linux 环境并启用 Xvfb + playwright chromium 路径

---

## 致谢

- [kevinr229/grok-maintainer](https://github.com/kevinr229/grok-maintainer) — 原始项目
- [grok2api](https://github.com/chenyme/grok2api) — Grok API 代理
- [DuckMail](https://duckmail.sbs) — 临时邮箱服务
- [temp-mail-api](https://temp-mail-api.deno.dev/docs) — 临时邮箱网关服务
