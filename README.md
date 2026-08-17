# A-Share Signal

A-Share Signal 是一个本地优先的 A 股研究工作台。它把行情、策略、任务和分析结果都落在本机 DuckDB 里，适合个人做日常复盘、策略筛选、盘中观察和候选跟踪。

它不是交易系统：不接券商账户，不做自动下单，也不提供投资建议。公网部署可以用可选 HTTP Basic Auth 保护整站。

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
Baostock history + AkShare Sina intraday
```

- 后端：FastAPI，负责 API、后台任务、数据同步、分析和静态文件托管。
- 前端：React + TypeScript + Vite，构建后由后端直接服务。
- 数据库：DuckDB，默认文件为 `data/ashare_signal.duckdb`，不会提交到 Git。
- 任务模型：GET 接口只读取已有状态；POST 接口显式启动后台任务。
- 分析边界：分析、回测和 AI 解释只读取 DuckDB 已持久化的数据，不会在页面查询时隐式抓行情。

## 数据边界

- Baostock：免费主源。负责股票基础信息、交易日历、前复权历史 K 线、换手率、PE/PB/PS/PCF、指数日线和行业分类。日更会用一个登录会话刷新所需股票的滚动前复权窗口，避免除权后历史口径漂移。
- AkShare 新浪：仅负责盘中/当天全市场快照。项目自己控制分页、请求超时、页间随机延迟、最短调用间隔和失败冷却；不会使用东财或腾讯备用源。
- Tushare：代码和历史表仍保留，但总开关默认关闭。只有显式设置 `ASHARE_TUSHARE_ENABLED=1` 后才会读取 token 并请求；旧增强数据有新鲜度上限，过期后不会继续参与当前分析。
- 本地缓存：页面刷新、服务重启、外部源失败时都从 DuckDB 恢复已有状态。

页面刷新、服务重启或网络临时不稳定时，前端继续读取 DuckDB 里已有的数据和任务状态。新闻资讯源不属于股票行情源，市场简报使用独立资讯抓取和 LLM 配置。

## 策略和分析

策略由一组可编辑规则组成。每次运行策略时，后端读取本地 DuckDB，构建分析帧，应用过滤、评分和排序规则，再把候选结果写回数据库。

分析任务默认分批读取历史 K 线，降低 2G 级别服务器上的内存峰值。RPS 和最终排序仍按全市场统一计算，不按批次排名，也不按批次截断。批大小可通过环境变量调整：

```bash
ASHARE_ANALYSIS_BATCH_SIZE=300
```

调小这个值会让分析更慢，但更省内存。

免费源支持的核心指标：

- 换手率：来自 Baostock 历史 K 线字段 `turn`；缺失会计入覆盖率，策略可选择跳过或降级。
- RPS：直接用本地历史收盘价计算 RPS20、RPS60、RPS120。计算方式为近 N 日涨幅在本地股票池中的百分位排名乘以 100。
- 振幅：直接用本地 K 线计算，`(high - low) / prev_close`。
- 流通市值：优先使用新浪原始 `nmc`；缺失时根据 Baostock 成交量和换手率估算流通股本并落入本地缓存。缺失不会导致分析失败。

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

默认盘中采样降为 9 个时点：

`09:40,10:10,10:40,11:10,13:10,13:40,14:10,14:40,14:55`

`ASHARE_INTRADAY_SCHEDULE` 是脚本、后端 scheduler 和状态页共同使用的时间表。轻量服务器上不建议全市场 5 分钟一次。

默认免费配置可从 `.env.example` 复制：

```bash
export ASHARE_LLM_ENABLED=0
export ASHARE_TUSHARE_ENABLED=0
export ASHARE_INTRADAY_SCHEDULER=1
export ASHARE_INTRADAY_SCHEDULE=09:40,10:10,10:40,11:10,13:10,13:40,14:10,14:40,14:55
export ASHARE_SINA_MIN_INTERVAL_MINUTES=12
export ASHARE_SINA_FAILURE_COOLDOWN_MINUTES=180
```

轻量日更会刷新最近 `ASHARE_HISTORY_DAYS` 天的 BaoStock 前复权窗口。市场环境使用 BaoStock 指数、本地市场宽度和当日涨跌幅估算；行业热力使用 BaoStock 行业分类和本地行情。

盘中调度只保留一套：默认使用进程内 scheduler。不要再同时启用外部 `ashare-intraday.timer`；如必须使用外部 timer，应设置 `ASHARE_INTRADAY_SCHEDULER=0`，两者只能选一个。

## 资讯简报

资讯简报会自动抓取国际科技、财经、时政等公开资讯源，保存原始条目和生成后的摘要到 DuckDB。默认每天北京时间 08:20 运行一次；也可以用逗号配置多个北京时间。 如果数据库里还没有任何简报，服务启动或打开首页时会自动排队生成第一份。

LLM 默认关闭。关闭时不会读取 `DEEPSEEK_API_KEY` 或 `ASHARE_DAILY_BRIEF_API_KEY`，资讯简报仍会抓取公开资讯并生成规则降级摘要。以后需要恢复时显式打开：

```bash
export ASHARE_LLM_ENABLED=1
export ASHARE_DAILY_BRIEF_API_KEY=your-api-key
export ASHARE_DAILY_BRIEF_MODEL=deepseek-chat
```

可选配置：

```bash
export ASHARE_DAILY_BRIEF_TIME=08:20,18:20
export ASHARE_DAILY_BRIEF_SCHEDULER=1
export ASHARE_DAILY_BRIEF_SOURCE_TIMEOUT=12
```

只在 `ASHARE_LLM_ENABLED=1` 时才会读取密钥。仅在 systemd 中残留旧 key 不会启用或调用 LLM。

候选股 AI 解读同样由后台任务处理。页面不会因为打开而调用模型；关闭 LLM 后保留任务和展示能力，但不会请求模型 API。

## 本地启动

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
ASHARE_LLM_ENABLED=0
ASHARE_TUSHARE_ENABLED=0
ASHARE_INTRADAY_SCHEDULER=1
ASHARE_INTRADAY_SCHEDULE=09:40,10:10,10:40,11:10,13:10,13:40,14:10,14:40,14:55
ASHARE_SINA_MIN_INTERVAL_MINUTES=12
ASHARE_SINA_FAILURE_COOLDOWN_MINUTES=180
ASHARE_ANALYSIS_BATCH_SIZE=300
ASHARE_DAILY_BRIEF_TIME=08:20,18:20
ASHARE_DAILY_UPDATE_SCHEDULER=0
```

需要恢复付费增强或 LLM 时，先分别设置 `ASHARE_TUSHARE_ENABLED=1` 或 `ASHARE_LLM_ENABLED=1`，再提供对应 token/key。

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
Environment="ASHARE_LLM_ENABLED=0"
Environment="ASHARE_TUSHARE_ENABLED=0"
Environment="ASHARE_ANALYSIS_BATCH_SIZE=300"
Environment="ASHARE_INTRADAY_SCHEDULER=1"
Environment="ASHARE_INTRADAY_SCHEDULE=09:40,10:10,10:40,11:10,13:10,13:40,14:10,14:40,14:55"
Environment="ASHARE_INTRADAY_RETENTION_DAYS=10"
Environment="ASHARE_DAILY_BRIEF_SCHEDULER=1"
Environment="ASHARE_DAILY_BRIEF_TIME=08:20,18:20"
# 公网部署请设置强随机密码，或在反向代理/VPN 层做等价保护。
Environment="ASHARE_HTTP_BASIC_USERNAME=replace-with-user"
Environment="ASHARE_HTTP_BASIC_PASSWORD=replace-with-strong-random-password"

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

如果当前 unit 里仍有 `DEEPSEEK_API_KEY`、`ASHARE_DAILY_BRIEF_API_KEY`、`ASHARE_TUSHARE_TOKEN` 或旧 Tushare 中转地址，可以直接删除；即使暂时没删，总开关为 `0` 时应用也不会读取密钥。unit 修改后先执行 `sudo systemctl daemon-reload`。公网不应在无认证情况下直接暴露服务端口。

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
