# A-Share Signal

A-Share Signal 是一个本地优先的 A 股研究工作台。它把行情、策略、任务和分析结果都落在本机 DuckDB 里，适合个人做日常复盘、策略筛选、盘中观察和候选跟踪。

它不是交易系统：不接券商账户，不做自动下单，也不提供投资建议。

## 主要功能

- 本地数据仓库：股票基础信息、历史 K 线、当天快照、资金流、涨跌停、筹码、题材、龙虎榜等数据统一写入 DuckDB。
- 策略选股：在网页里配置价格、成交额、RPS、均线、平台、趋势、题材、资金和风险条件，后台生成候选结果。
- AI 候选解读：分析完成后自动为候选股生成结构化解释，页面只读取已有结果和任务状态。
- 盘中雷达：盘中采样写入本地仓库。三张盘中榜默认关闭，需要时手动开启；策略跟踪由用户手动触发。
- 观察池：把候选股加入观察池，记录假设、入选理由、备注和后续表现。
- 回测：支持信号评估和简化组合模拟，用本地历史数据检验策略表现。
- 市场简报：自动抓取资讯并调用配置好的 LLM 生成中文简报。资讯链路独立于股票行情数据。
- 任务状态：数据同步、分析、回测、盘中采样和 AI 解读都走后台任务，前端轮询真实进度。

## 架构

```text
React + Vite frontend
        |
FastAPI API and static hosting
        |
DuckDB local warehouse
        |
Tushare market-data sync tasks
```

- 后端：FastAPI，负责 API、后台任务、数据同步、分析和静态文件托管。
- 前端：React + TypeScript + Vite，构建后由后端直接服务。
- 数据库：DuckDB，默认文件为 `data/ashare_signal.duckdb`，不会提交到 Git。
- 任务模型：GET 接口只读取已有状态；POST 接口显式启动后台任务。
- 分析边界：分析、回测和 AI 解释只读取 DuckDB 已持久化的数据，不会在页面查询时隐式抓行情。

## 数据边界

股票行情和股票增强数据只使用 Tushare：

- `stock_basic`：股票基础信息。
- `daily`、`adj_factor`、`daily_basic`：前复权历史 K 线、换手率、流通市值。
- 实时日线接口：盘中快照和当天数据。
- `stk_factor`、`moneyflow`、`limit_list_d`、`cyq_perf`、`cyq_chips`、`ths_member`、`top_list`、`top_inst`、`hm_detail`：策略特征、展示字段和风险证据。
- `index_daily`：指数和市场环境计算。

页面刷新、服务重启或网络临时不稳定时，前端继续读取 DuckDB 里已有的数据和任务状态。新闻资讯源不属于股票行情源，市场简报使用独立资讯抓取和 LLM 配置。

## 策略和分析

策略由一组可编辑规则组成。每次运行策略时，后端读取本地 DuckDB，构建分析帧，应用过滤、评分和排序规则，再把候选结果写回数据库。

分析任务默认分批读取历史 K 线，降低 2G 级别服务器上的内存峰值。RPS 和最终排序仍按全市场统一计算，不按批次排名，也不按批次截断。批大小可通过环境变量调整：

```bash
ASHARE_ANALYSIS_BATCH_SIZE=300
```

调小这个值会让分析更慢，但更省内存。

## 盘中雷达

盘中雷达分为两类：

- 策略跟踪：用户选择一个已有策略，手动触发一次盘中策略跟踪。
- 盘中榜单：异动、低吸、风险三张榜默认关闭。开启后，系统按盘中计划采样并生成榜单。

当三张榜都关闭时，盘中任务会使用较低频率做轻量刷新，主要用于保持首页和市场信息更新。

手动采样一次：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/tasks/intraday-snapshot \
  -H 'Content-Type: application/json' \
  -d '{}'
```

查看盘中数据：

```bash
curl -sS http://127.0.0.1:8000/api/intraday/boards
curl -sS http://127.0.0.1:8000/api/intraday/strategy-tracking
```

## 市场简报和 LLM

市场简报默认由后台调度器自动运行，时间由 `ASHARE_DAILY_BRIEF_TIME` 控制，支持逗号分隔多个时间，例如：

```bash
ASHARE_DAILY_BRIEF_TIME=08:20,18:20
ASHARE_DAILY_BRIEF_SCHEDULER=1
ASHARE_DAILY_BRIEF_API_KEY=your-key
ASHARE_DAILY_BRIEF_MODEL=deepseek-chat
ASHARE_DAILY_BRIEF_LLM_URL=https://api.deepseek.com/chat/completions
```

候选股 AI 解读同样由后台任务自动处理。页面不会提供“生成按钮”，也不会因为打开页面而调用模型。

## 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

npm --prefix frontend install
npm --prefix frontend run build

python scripts/init_db.py
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

前端开发模式：

```bash
npm --prefix frontend run dev
```

Vite 开发服务器会把 `/api` 代理到 `127.0.0.1:8000`。

## 环境变量

可以从 `.env.example` 复制一份：

```bash
cp .env.example .env
```

常用配置：

```bash
ASHARE_TUSHARE_TOKEN=your-token
ASHARE_TUSHARE_HTTP_URL=http://101.35.233.113:8020/
ASHARE_TUSHARE_REALTIME=1
ASHARE_TUSHARE_HISTORY=1
ASHARE_TUSHARE_ENRICHMENT=1
ASHARE_TUSHARE_HISTORY_TIMEOUT=900
ASHARE_TUSHARE_ENRICHMENT_CODE_LIMIT=200
ASHARE_ANALYSIS_BATCH_SIZE=300

ASHARE_DAILY_BRIEF_API_KEY=your-llm-key
ASHARE_DAILY_BRIEF_MODEL=deepseek-chat
ASHARE_DAILY_BRIEF_LLM_URL=https://api.deepseek.com/chat/completions
ASHARE_DAILY_BRIEF_TIME=08:20,18:20
```

## systemd 部署示例

线上目录示例使用 `/opt/astock`，服务名为 `ashare-signal`。端口可以按服务器实际反向代理配置调整，下面使用 `8765`。

```ini
[Unit]
Description=A-Share Signal
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/astock
ExecStart=/opt/astock/.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5
Environment="ASHARE_DB_PATH=/opt/astock/data/ashare_signal.duckdb"
Environment="ASHARE_TUSHARE_TOKEN=replace-with-your-token"
Environment="ASHARE_TUSHARE_HTTP_URL=http://101.35.233.113:8020/"
Environment="ASHARE_TUSHARE_REALTIME=1"
Environment="ASHARE_TUSHARE_HISTORY=1"
Environment="ASHARE_TUSHARE_ENRICHMENT=1"
Environment="ASHARE_ANALYSIS_BATCH_SIZE=300"
Environment="ASHARE_INTRADAY_SCHEDULER=1"
Environment="ASHARE_DAILY_BRIEF_SCHEDULER=1"
Environment="ASHARE_DAILY_BRIEF_TIME=08:20,18:20"
Environment="ASHARE_DAILY_BRIEF_API_KEY=replace-with-your-key"
Environment="ASHARE_DAILY_BRIEF_MODEL=deepseek-chat"

[Install]
WantedBy=multi-user.target
```

更新部署：

```bash
sudo systemctl stop ashare-signal

cd /opt/astock
git fetch origin
git pull --ff-only origin main

. .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python scripts/init_db.py

sudo systemctl start ashare-signal
sudo systemctl status ashare-signal --no-pager -l
```

## 备份

DuckDB 是项目的核心状态文件。更新前建议备份：

```bash
python scripts/backup_db.py
```

备份文件会写入 `data/backups/`。

## 快速检查

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/runtime/health
curl http://127.0.0.1:8000/api/bootstrap
curl http://127.0.0.1:8000/api/tasks?status=queued,running
curl http://127.0.0.1:8000/api/analysis/reports
curl http://127.0.0.1:8000/api/daily-brief
curl http://127.0.0.1:8000/api/data/overview
```

如果线上服务使用 `8765`，把命令中的端口改成 `8765`。
