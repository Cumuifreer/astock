# A-Share Signal

A-Share Signal 是一个本地优先的 A 股收盘选股与复盘工作台，面向个人使用。它把免费数据、策略、任务、分析结果和观察池保存在 DuckDB 中，由 FastAPI 提供接口和静态页面。

## 当前工作流

网页只保留四个入口：

- **收盘复盘**：查看最近一次分析报告、候选股、筛选证据和交易日，并把候选加入观察池。
- **策略选股**：从可执行指标库中选择规则，保存策略并启动一次收盘后分析。
- **观察池**：记录候选股的入选日期、理由、备注和后续状态。
- **数据与任务**：查看免费数据覆盖情况，手动刷新日线数据和分析任务进度。

项目不接券商账户，不自动下单，也不在网页打开时调用外部行情或 LLM。盘中雷达、付费 Tushare、AkShare 新浪快照、市场简报、候选股 AI 解读和回测入口已经从主流程移除；数据库中的旧表保留用于兼容迁移。

## 数据和性能边界

- Baostock 是唯一行情源，使用日线和交易日历，历史 K 线按前复权口径保存。
- 收盘复盘严格按同一个历史交易日读取 K 线、换手率、成交额、涨跌幅和估算流通市值，避免当前快照污染旧报告。
- DuckDB 连接默认限制为 512MB 和 2 个线程；分析按批读取，适合 2G/2C 的个人服务器。
- 数据更新默认手动触发。需要每天自动刷新时设置 `ASHARE_DAILY_UPDATE_SCHEDULER=1`，时间由 `ASHARE_DAILY_UPDATE_TIME` 控制。

## 本地启动

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/init_db.py
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

打开 `http://127.0.0.1:8000`。

常用环境变量：

```bash
ASHARE_DB_PATH=data/ashare_signal.duckdb
ASHARE_HISTORY_DAYS=550
ASHARE_ANALYSIS_BATCH_SIZE=200
ASHARE_DB_MEMORY_LIMIT=512MB
ASHARE_DB_THREADS=2
ASHARE_DAILY_UPDATE_SCHEDULER=0
ASHARE_DAILY_UPDATE_TIME=18:30
ASHARE_HTTP_BASIC_USERNAME=
ASHARE_HTTP_BASIC_PASSWORD=
```

`.env.example` 中只保留当前免费日线工作流需要的配置。旧的 Tushare、LLM、盘中和新浪配置会被忽略。

## 服务器更新

服务器目录示例为 `/opt/astock`，systemd 服务名为 `ashare-signal`，端口为 `8765`。

```bash
cd /opt/astock
sudo systemctl stop ashare-signal
mkdir -p data/backups
cp -a data/ashare_signal.duckdb data/backups/ashare_signal.before-update-$(date +%Y%m%d%H%M%S).duckdb
git fetch origin
git pull --ff-only origin main
. .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
sudo systemctl start ashare-signal
sudo systemctl status ashare-signal --no-pager -l
```

启动时会自动执行数据库迁移。更新后可检查：

```bash
curl -sS http://127.0.0.1:8765/api/health
curl -sS http://127.0.0.1:8765/api/review/overview
```

公网部署建议启用 HTTP Basic Auth，或在反向代理/VPN 层做访问控制。
