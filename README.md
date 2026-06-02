# A-Share Signal

A-Share Signal 是一个私人使用的 A 股技术分析 Web 应用。它只做本地数据缓存、技术策略配置、后台分析和候选解释，不接券商账户，不做登录权限，也不做自动交易。

## 架构

- 后端：FastAPI，负责 API、后台任务、数据源适配和前端静态文件托管。
- 数据仓库：DuckDB，默认文件为 `data/ashare_signal.duckdb`，不会提交到 Git。
- 前端：Vite + React + TypeScript，构建产物由后端托管。
- 任务：数据更新和分析分开运行；点击后立即返回，前端轮询真实进度。
- 盘中雷达：可手动或用定时器触发全市场快照采样，采样入库后自动生成独立观察榜，不覆盖正式分析报告。
- 资讯简报：新闻源和 LLM 独立于股票数据源；后台调度器自动抓取资讯并写入 DuckDB，首页只读取已有简报和任务状态。

## 数据源

- Tushare 历史日线：通过 `daily`、`adj_factor` 和 `daily_basic` 批量生成前复权 K 线，保存成交量、成交额和换手率 `turn`。
- Tushare 实时日线：配置 token 后，数据更新和盘中雷达会用 Tushare 中转实时 K 线采样，并同步写入当天快照。
- Tushare 增强数据：`daily_basic`、`stk_factor`、`moneyflow`、`limit_list_d`、`cyq_perf`、`cyq_chips`、`ths_member`、`top_list`、`top_inst`、`hm_detail` 会写入本地仓库供分析和个股档案使用。
- 本地 DuckDB 缓存：页面刷新、服务重启或 Tushare 暂不可用时，前端读取已经入库的本地数据和任务状态。

项目除 Tushare 外不接入其他行情接口；数据地图只展示 Tushare 同步状态和本地 DuckDB 缓存状态。

## 指标

- 换手率：优先来自 Tushare `daily_basic` 并写入历史 K 线字段 `turn`；缺失会计入覆盖率，策略可选择跳过或降级。
- RPS：直接用本地历史收盘价计算 RPS20、RPS60、RPS120。计算方式为近 N 日涨幅在本地股票池中的百分位排名乘以 100。
- 振幅：直接用本地 K 线计算，`(high - low) / prev_close`。
- 流通市值：优先使用本地缓存；Tushare `daily_basic` 提供流通市值字段时写入缓存。缺失时按策略配置跳过或降级，不会导致分析失败。

## 盘中雷达

盘中雷达使用独立配置和独立表，不会覆盖日线快照、候选股票或报告库。它会在每次盘中采样后自动计算观察榜，主要用于发现“接近平台上沿 / 刚突破但未过热 / 盘中成交额放大”的股票。

手动触发一次采样：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/tasks/intraday-snapshot \
  -H 'Content-Type: application/json' \
  -d '{}'
```

查看状态和最新观察榜：

```bash
curl -sS http://127.0.0.1:8000/api/status/intraday
curl -sS http://127.0.0.1:8000/api/intraday
```

默认盘中采样时间为 10 分钟一档：

`09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55`

`ASHARE_INTRADAY_SCHEDULE` 是脚本、后端 scheduler 和状态页共同使用的时间表。轻量服务器上不建议全市场 5 分钟一次。

盘中雷达使用 Tushare 实时日线写入当天快照；Tushare 暂不可用时，页面继续展示 DuckDB 里已有的最近数据。Tushare 初始化集中在 `backend/app/sources/tushare_client.py`，所有调用都会设置中转地址 `pro._DataApi__http_url = "http://101.35.233.113:8020/"`。密钥只从环境变量或项目根目录 `.env` 读取，不要写进代码；可从 `.env.example` 复制本机配置：

```bash
export ASHARE_TUSHARE_TOKEN=your-token
export ASHARE_TUSHARE_HTTP_URL=http://101.35.233.113:8020/
export ASHARE_TUSHARE_REALTIME=1
export ASHARE_TUSHARE_HISTORY=1
export ASHARE_TUSHARE_HISTORY_TIMEOUT=900
export ASHARE_TUSHARE_ENRICHMENT=1
export ASHARE_TUSHARE_ENRICHMENT_CODE_LIMIT=200
export ASHARE_INTRADAY_SCHEDULE=09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55
export ASHARE_INTRADAY_RETENTION_DAYS=0
```

轻量日更补齐历史 K 线后，会按 `ASHARE_INTRADAY_RETENTION_DAYS` 清理已落入历史 K 线的旧盘中快照和盘中排名。设为 `0` 会清掉所有符合条件的历史盘中行，设为负数会关闭清理。

Tushare 历史 K 线会在轻量日更时刷新最近 `ASHARE_HISTORY_DAYS` 天的前复权窗口，用最新 `adj_factor` 重新写入近期 OHLC，避免除权后只补当天导致历史口径漂移。刷新过程按交易日流式写入 DuckDB，并在状态页显示当前日期、接口步骤、已写入行数和心跳时间；服务中途重启时，已经写入的日期会保留。

轻量/完整更新会在历史 K 线后接入 Tushare 增强数据：`daily_basic`、`stk_factor`、`moneyflow`、`limit_list_d`、`cyq_perf`、`cyq_chips`、`ths_member`、`top_list`、`top_inst`、`hm_detail`。其中 `daily_basic` 会直接写入流通市值缓存；筹码和同花顺成分会按 `ASHARE_TUSHARE_ENRICHMENT_CODE_LIMIT` 分批补齐。

市场环境会优先抓取 Tushare `index_daily` 指数日线，并结合本地历史 K 线宽度、成交额和涨跌停事件生成市场温度。数据仓库页可从股票列表点开个股档案，查看每日指标、资金流、筹码、题材和事件数据。

如果用 systemd 定时触发，可以让 timer 在这些时间运行：

```ini
[Unit]
Description=A-Share Signal Intraday Snapshot

[Service]
Type=oneshot
WorkingDirectory=/opt/ashare-signal
Environment=ASHARE_BASE_URL=http://127.0.0.1:8000
Environment=ASHARE_INTRADAY_SCHEDULE=09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55
ExecStart=/opt/ashare-signal/.venv/bin/python scripts/run_intraday_snapshot.py
```

```ini
[Unit]
Description=A-Share Signal Intraday Snapshot Timer

[Timer]
OnCalendar=Mon..Fri 09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55
Persistent=false

[Install]
WantedBy=timers.target
```

## 资讯简报

Tushare-only 只约束股票行情、基础信息和增强数据；资讯简报使用新闻/RSS 内容源和配置好的 LLM 生成中文摘要。页面 GET 只读取 DuckDB 已有简报和后台任务状态，不会因为打开网页而抓取资讯或调用模型。

默认启用后台资讯简报调度，时间由 `ASHARE_DAILY_BRIEF_TIME` 控制，默认 `08:20`；可用逗号配置多个时间，例如 `08:20,18:20`。`ASHARE_DAILY_BRIEF_SCHEDULER=0` 可关闭调度。`POST /api/daily-brief/regenerate` 仅作为明确的后台任务入口使用，前端不会展示手动生成按钮。

## 本地启动

```bash
python3 -m pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python3 scripts/init_db.py
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

打开 `http://127.0.0.1:8000`。

开发前端时可以另开 Vite：

```bash
npm --prefix frontend run dev
```

Vite 会把 `/api` 代理到 `127.0.0.1:8000`。

## Ubuntu 部署

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm git
git clone <your-repo-url> /opt/ashare-signal
cd /opt/ashare-signal
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python scripts/init_db.py
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

更新部署：

```bash
cd /opt/ashare-signal
git pull
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python scripts/init_db.py
sudo systemctl restart ashare-signal
```

## systemd 示例

```ini
[Unit]
Description=A-Share Signal
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/ashare-signal
Environment="ASHARE_DB_PATH=/opt/ashare-signal/data/ashare_signal.duckdb"
Environment="ASHARE_TUSHARE_TOKEN=replace-with-your-token"
Environment="ASHARE_TUSHARE_HTTP_URL=http://101.35.233.113:8020/"
Environment="ASHARE_TUSHARE_REALTIME=1"
Environment="ASHARE_INTRADAY_SCHEDULE=09:35,09:45,09:55,10:05,10:15,10:25,10:35,10:45,10:55,11:05,11:15,11:25,13:00,13:10,13:20,13:30,13:40,13:50,14:00,14:10,14:20,14:30,14:40,14:50,14:55"
Environment="ASHARE_INTRADAY_RETENTION_DAYS=10"
ExecStart=/opt/ashare-signal/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 备份

```bash
python scripts/backup_db.py
```

备份文件会写入 `data/backups/`。

## API 快速检查

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/bootstrap
curl http://127.0.0.1:8000/api/status/update
curl http://127.0.0.1:8000/api/status/analyze
curl http://127.0.0.1:8000/api/status/intraday
curl http://127.0.0.1:8000/api/daily-brief
curl http://127.0.0.1:8000/api/candidates
curl http://127.0.0.1:8000/api/data/overview
curl http://127.0.0.1:8000/api/data/capabilities
```
