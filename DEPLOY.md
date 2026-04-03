# 云端部署说明

目标：用户只需在浏览器打开**固定网址**，无需在本地安装 Python / Node，也无需运行 `start.bat`。

本项目在开发时拆成三部分（Vite 前端、`/ecm` Python、`/api` Node）。线上通过 **一个 Node 网关**（`server/prod.js`）合并为同一域名：

- 静态页面：`/` → `dist/`
- 聊天代理：`/api` → Node（DeepSeek）
- ECM 后端：`/ecm` → Python（Waitress，Flask）

## 1. 环境变量（必填）

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（与本地 `.env` 相同） |
| `ECM_ADMIN_SECRET`（可选） | 仅你使用的审计总览：浏览器打开 `https://你的域名/audit-console`，密钥与此变量一致 |

云平台一般会注入 `PORT`（对外监听端口），**不要**在面板里手动改 `ECM_BACKEND_URL`（容器内 Python 固定在 `127.0.0.1:9000`）。

### 审计总览（仅部署者）

1. 在云平台环境变量中设置较长的随机字符串：`ECM_ADMIN_SECRET=...`
2. 重新部署
3. 浏览器访问：`https://你的域名/audit-console`
4. 在页面输入同一串密钥（会保存在本机 `sessionStorage`，勿在公共电脑使用）

可查看：最近 `/ecm/*` 请求（含客户端 IP、`userId`/登录用户名）、用户列表（不含密码）、项目列表、Analytics 表行数与样本行、笔记区元数据统计。

## 2. 用 Docker 一键部署（推荐）

在项目根目录：

```bash
docker build -t ecm-app .
docker run --rm -p 8080:8080 -e DEEPSEEK_API_KEY=你的密钥 ecm-app
```

浏览器访问 `http://服务器IP:8080` 即可。

## 3. Render（示例）

1. 将代码推送到 GitHub。
2. Render → **New** → **Blueprint** → 选择 `render.yaml`。
3. 在面板中为服务设置 `DEEPSEEK_API_KEY`。
4. 部署完成后使用 Render 提供的 `https://xxx.onrender.com` 访问。

## 4. 数据持久化说明

用户与项目等 JSON、以及 **`analytics.db` / `sessions.db`** 均落在 **`ECM_DATA_DIR`**（默认项目根目录下的 `data/`）。在 Docker / Railway 中设置 **`ECM_DATA_DIR=/app/data`** 并为 **`/app/data` 挂载一个 Volume** 即可持久化全部文件数据，**无需第二个卷**。容器**无持久卷**时，重部署会清空数据（或改用托管数据库）。

### 4.1 内置测试种子数据（Git 仓库内）

仓库包含 `seed/data/`（示例用户、项目、画像、笔记）。**首次启动**且 `ECM_DATA_DIR` 下尚无 `users.json` 时，会自动复制到数据目录，并在 analytics 库为空时写入示例分析行。测试账号：`demo` / `demo123456`（验证码按登录页类型填写）。生产环境若不要种子，可设置环境变量 `ECM_DISABLE_SEED=1`。

### 4.2 将 `data/` 提交到 Git（仅建议私有仓库）

若把 **`data/`**（含 `users.json`、`projects.json`、SQLite 等）提交到仓库，Docker 构建会额外复制到 **`/app/_baked_data`**。部署后若 **`ECM_DATA_DIR` 为空卷**（尚无 `users.json`），进程会从该备份自动恢复到 `ECM_DATA_DIR`，无需手动上传。**切勿在公开仓库中提交真实用户密码与对话**；若必须提交，请使用 **GitHub Private** 仓库。设置 **`ECM_SKIP_BAKED_RESTORE=1`** 可关闭自动恢复。

## 5. 本地模拟“云端”单端口（可选）

先构建前端，再分别启动 Python 与网关（二选一）：

**Linux / macOS / Git Bash**

```bash
npm run build
chmod +x scripts/start-prod.sh
./scripts/start-prod.sh
```

**Windows（两个终端）**

终端 A：`waitress-serve --listen=127.0.0.1:9000 app.main:app`  
终端 B：`set PORT=8080&& npm start`（需已执行 `npm run build`）

访问 `http://127.0.0.1:8080`。
