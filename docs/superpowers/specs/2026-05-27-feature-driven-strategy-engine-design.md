# 特征驱动策略引擎设计

日期：2026-05-27

## 背景

当前策略系统已经把“指标库”和“策略页按分类摆参数”的方向搭起来了，但底层仍保留旧心智：

- `signal_mode` 仍决定平台突破、平台临界、趋势共振等内部执行分支。
- `strategy_interactions` 仍以组合倍率影响最终分数。
- 一些 Tushare 数据已经入库并能在数据仓库查看，但没有进入正式分析帧，只能作为观察字段。
- 策略页虽然移除了单指标规则入口，但仍有“组合倍率”等旧概念，用户会误以为系统还在靠隐藏模式运行。

本次重构目标是把策略系统改成特征驱动：所有可用数据先转换为可解释的股票特征，再由统一策略参数和评分规则执行。用户不再选择信号模式，也不再配置 interaction terms。

## 目标

1. 移除用户可见和运行时依赖的信号模式。
2. 移除 strategy interactions / 组合倍率，不再用隐藏乘数影响分数。
3. 把已有 Tushare 数据转换为有意义、可解释、可筛选或可评分的策略参数。
4. 策略页继续采用按指标分类摆放的 UI，但每个字段都要说明单位、含义、推荐范围和数据状态。
5. 旧自定义策略尽量保留已经填写好的值；只有语义明确、低风险的参数自动迁移。
6. 新引擎输出每个候选的过滤、评分、风险和解释明细，让用户知道结果从哪里来。

## 非目标

- 不做公式编辑器、Pine Script 或任意表达式语言。
- 不做自动交易、券商接入或权限系统。
- 不把旧 signal mode 原样包一层继续运行。
- 不为了保留旧值而迁移高风险的隐式组合逻辑。
- 不一次性承诺所有低覆盖 Tushare 字段都可硬筛选；覆盖不足时只能评分、展示或作为风险提示。

## 核心原则

策略不再是“模式 + 参数”，而是：

```text
本地数据 / Tushare 数据 -> feature_frame -> 指标参数 -> 过滤 / 评分 / 风险 -> 候选解释
```

每个进入策略页的指标必须回答：

- 它是什么。
- 怎么算。
- 单位是什么。
- 覆盖率和最新日期是什么。
- 可用于硬筛选、评分、风险、展示中的哪些用途。
- 缺失时如何处理。

不再让用户选择“平台突破 / 趋势共振 / 题材共振突破”。这些概念会拆成可见指标，例如平台振幅、距平台上沿、突破上沿距离、均线多头、题材热度、量比、主力净额。

## 新策略配置

新增统一配置结构，旧 `StrategyConfig` 逐步迁移为：

```ts
type StrategyConfigV2 = {
  version: 2;
  name?: string;
  universe: UniverseConfig;
  filters: StrategyCondition[];
  scores: StrategyScoreRule[];
  risks: StrategyRiskRule[];
  display: string[];
  output: OutputConfig;
  migration?: MigrationInfo;
};
```

### UniverseConfig

基础股票池。保留旧策略里低风险且语义明确的值：

- 最低股价。
- 最低成交额。
- 流通市值上下限。
- 是否包含北交所。
- 是否排除科创板。
- ST / 停牌过滤。
- 换手率缺失处理。
- 流通市值缺失处理。

### StrategyCondition

硬筛选条件：

```ts
type StrategyCondition = {
  id: string;
  indicator_id: string;
  operator: "gte" | "lte" | "gt" | "lt" | "between" | "eq" | "neq" | "recent";
  value?: number | string | boolean;
  value2?: number | string;
  window_days?: number;
  missing_policy: "skip" | "keep";
  enabled: boolean;
};
```

硬筛选只适合覆盖稳定、含义明确的指标。低覆盖事件类指标默认不做硬筛选。

### StrategyScoreRule

评分规则：

```ts
type StrategyScoreRule = {
  id: string;
  indicator_id: string;
  direction: "higher_better" | "lower_better" | "range_better";
  weight: number;
  target?: number;
  min_value?: number;
  max_value?: number;
  missing_policy: "neutral" | "penalty";
  enabled: boolean;
};
```

评分采用加权模型，不再使用组合倍率。多个指标同时优秀时自然叠加，结果解释里写明“题材、量能、位置同时确认”。

### StrategyRiskRule

风险规则用于扣分或标记：

```ts
type StrategyRiskRule = {
  id: string;
  indicator_id: string;
  operator: "gte" | "lte" | "gt" | "lt" | "between" | "eq" | "recent";
  value?: number | string | boolean;
  value2?: number | string;
  penalty: number;
  missing_policy: "neutral" | "keep";
  enabled: boolean;
};
```

## 指标分类

策略页继续按分类展示，不做传统后台式参数墙。

### 基础股票池

- 最新价。
- 成交额。
- 流通市值。
- 总市值。
- 北交所 / 科创板范围。
- ST / 停牌。
- 数据缺失处理。

### 基础行情

- 涨跌幅。
- 振幅。
- 换手率。
- 量比。
- 成交额扩张。
- 近 N 日成交额均值。

### 技术强弱

- RPS20 / RPS60 / RPS120。
- MA 多头。
- MA 距离。
- MACD 状态。
- KDJ 状态。
- RSI6 / RSI12 / RSI24。
- BOLL 位置。
- CCI。

### 平台形态

- 平台观察天数。
- 平台振幅。
- 平台阳线占比。
- 阳线均量优势。
- 距平台上沿。
- 突破上沿距离。
- 首次突破天数。
- 突破量比。
- 近 5 日涨幅。

这些不再对应“平台突破模式”，只是普通特征。

### 题材行业

- 题材数量。
- 最强题材名称。
- 题材热度。
- 题材内排名。
- 题材内 RPS 高分股比例。
- 题材平均涨幅。
- 题材涨停数。
- 题材成交额扩张。
- 是否新纳入题材。

A 股当前偏热门板块交易，这组指标应成为策略页的一等公民。

### 资金流向

- 主力净额。
- 主力净额 / 成交额。
- 全口径资金净流入。
- 超大单净额。
- 大单净额。
- 连续净流入天数。
- 资金流强度分。

### 涨跌停事件

- 最近 N 日涨停。
- 最近 N 日跌停。
- 最近 N 日炸板。
- 开板次数。
- 封单金额。
- 封单金额 / 流通市值。
- 连板或反包事件标签。

### 龙虎榜 / 游资

- 最近 N 日上榜。
- 龙虎榜净买额。
- 龙虎榜净买额 / 成交额。
- 机构净买额。
- 游资席位净买额。
- 上榜原因标签。

覆盖不稳定时默认展示或评分，不默认硬筛。

### 筹码成本

- 获利盘比例。
- 中位成本。
- 当前价距中位成本。
- 成本 15% / 85% 区间宽度。
- 上方压力距离。
- 筹码集中度。

### 市场环境

- 市场宽度。
- 指数趋势分。
- 市场风险等级。
- 涨停家数。
- 跌停家数。
- 强势股数量。
- 弱势股数量。
- 全市场成交额。

市场环境默认作为全局评分或风险调整，不作为个股硬筛。

## Tushare 数据到特征映射

| 数据表 | 原始字段 | 新特征 |
| --- | --- | --- |
| `daily_basic` | `turnover_rate` | 换手率 |
| `daily_basic` | `volume_ratio` | 量比 |
| `daily_basic` | `total_mv`, `circ_mv` | 总市值、流通市值 |
| `daily_basic` | `pe`, `pb`, `ps` | 估值观察字段 |
| `stk_factor` | `macd` | MACD 动能 |
| `stk_factor` | `kdj_k`, `kdj_d`, `kdj_j` | KDJ 状态 |
| `stk_factor` | `rsi_6`, `rsi_12`, `rsi_24` | RSI 强弱 |
| `stk_factor` | `boll_upper`, `boll_mid`, `boll_lower` | BOLL 位置 |
| `stk_factor` | `cci` | CCI 强弱 |
| `moneyflow` | `main_net_amount` | 主力净额 |
| `moneyflow` | `net_mf_amount` | 资金净流入 |
| `moneyflow` | 大小单买卖金额 | 超大单 / 大单 / 中小单净额 |
| `limit_list_d` | `limit_type` | 涨停 / 跌停 / 炸板状态 |
| `limit_list_d` | `open_times` | 开板次数 |
| `limit_list_d` | `fd_amount` | 封单金额 |
| `cyq_perf` | `winner_rate` | 获利盘比例 |
| `cyq_perf` | `cost_50pct` | 中位成本 |
| `cyq_perf` | `cost_15pct`, `cost_85pct` | 筹码区间宽度 |
| `cyq_chips` | `price`, `percent` | 成本分布集中度 |
| `ths_member` | `con_code`, `con_name`, `weight`, `is_new` | 题材归属、题材权重、新题材 |
| `top_list` | `net_amount`, `amount_rate`, `reason` | 龙虎榜净买、成交占比、上榜原因 |
| `top_inst` | `net_buy` | 机构席位净买 |
| `hm_detail` | `hm_name`, `net_amount` | 游资席位净买 |
| `market_environment` | 全字段 | 市场宽度、风险、指数、涨跌停温度 |

## feature_frame

新增统一分析帧构造层，替代“按 signal_mode 决定算什么”的方式。

### 输入

- 最新历史 K 线。
- 当天快照。
- 流通市值缓存。
- Tushare daily_basic。
- Tushare stk_factor。
- Tushare moneyflow。
- Tushare limit_list_d。
- Tushare cyq_perf / cyq_chips。
- Tushare ths_member。
- Tushare top_list / top_inst / hm_detail。
- 市场环境。

### 输出

每只股票一行，字段包括：

- 基础字段：代码、名称、价格、涨跌幅、成交额、市值、换手率、量比。
- 技术字段：RPS、均线、振幅、MACD、KDJ、RSI、BOLL、CCI。
- 平台字段：平台振幅、距平台上沿、突破距离、首次突破天数、平台量价结构。
- 题材字段：题材数、最强题材、题材热度、题材内排名、题材涨停数。
- 资金字段：主力净额、净流入、大小单净额、连续流入天数。
- 事件字段：涨跌停、开板次数、封单额、龙虎榜、游资、机构。
- 筹码字段：获利盘、中位成本距离、成本集中度、压力距离。
- 环境字段：市场趋势、风险等级、宽度分。
- 元数据：每组数据的来源、日期、覆盖状态。

## 运行流程

1. 读取并归一化 `StrategyConfigV2`。
2. 构建 `feature_frame`。
3. 执行基础股票池过滤。
4. 执行用户启用的硬筛选条件。
5. 计算评分规则。
6. 计算风险扣分。
7. 应用市场环境全局调整。
8. 排序并截取候选。
9. 保存候选、漏斗、分项得分和解释。

## 评分模型

总分建议拆成固定维度：

- `position_score`：位置与买点质量。
- `volume_score`：量能与流动性。
- `strength_score`：RPS、趋势、技术强弱。
- `theme_score`：题材热度与板块地位。
- `capital_score`：资金流向。
- `event_score`：涨停、龙虎榜、游资等事件。
- `chip_score`：筹码结构。
- `environment_score`：市场顺风程度。
- `risk_penalty`：过热、炸板、缺失、异常风险。

最终：

```text
strategy_score =
  position_score
  + volume_score
  + strength_score
  + theme_score
  + capital_score
  + event_score
  + chip_score
  + environment_score
  - risk_penalty
```

不再乘 `strategy_interactions`。

## 旧策略迁移

迁移原则：尽量保留已有值，但不为高风险迁移牺牲稳定性。

### 直接迁移

以下字段语义明确，自动迁移：

- `min_price` -> universe 最低股价。
- `min_amount` -> universe 成交额门槛。
- `min_float_market_value` / `max_float_market_value` -> universe 流通市值范围。
- `include_bj` / `exclude_star_board` -> universe 市场范围。
- `missing_turnover_policy` / `missing_float_market_value_policy` -> 缺失处理。
- `candidate_limit` -> output 候选上限。
- `sort_by` -> output 排序。
- `min_rps20` / `min_rps60` / `min_rps120` -> RPS 硬筛或评分阈值。
- `min_turnover` / `max_turnover` -> 换手率条件。
- `min_pct_chg` / `max_pct_chg` -> 涨跌幅条件。
- `max_amplitude` -> 振幅风险或过滤。
- `volume_ratio_min` -> 量比条件。
- `max_ma_distance` -> 均线偏离风险。
- `min_topic_count` -> 题材数条件。
- `min_topic_heat` -> 题材热度条件。
- `min_theme_limit_count` -> 题材涨停数条件。
- `platform_lookback_days`、`platform_max_range`、`platform_breakout_clearance`、`platform_breakout_max_clearance`、`platform_setup_max_distance_to_high` -> 平台形态参数。
- `trend_ema_*`、`trend_macd_*`、`trend_stoch_*` -> 技术指标周期参数。

### 谨慎迁移

以下字段可迁移为默认启用的评分或风险项，但不保证完全复刻旧行为：

- `platform_*_mode` 中的 `must` / `score` / `off`。
- `platform_breakout_first_mode`。
- `platform_ma_bullish_mode`。
- `platform_macd_filter_mode`。
- `trend_entry_signal`。
- `trend_macd_mode`。
- `trend_stoch_mode`。

迁移方式：

- `must` 迁为过滤条件。
- `score` 迁为评分规则。
- `off` 不启用。

如果字段依赖旧 signal mode 上下文才有意义，迁移时记录 warning，但不阻断保存。

### 不迁移

以下内容不迁移：

- `signal_mode` 的模式选择语义。
- `strategy_interactions` 组合倍率。
- `signal_profile` 中的 rule_groups。
- 任何没有明确指标字段或执行口径的旧隐藏规则。

旧配置加载后保留 `migration` 元信息：

```ts
type MigrationInfo = {
  from_version: 1;
  migrated_at: string;
  preserved_fields: string[];
  dropped_fields: string[];
  warnings: string[];
};
```

用户可以看到“哪些值已保留、哪些旧逻辑已丢弃”，但不需要处理技术细节。

## 前端设计

沿用当前金融终端风格：深色、紧凑、密度高、按分类浏览。不要做营销式页面，不要做卡片套卡片。

### 策略页结构

1. 左侧策略库：我的策略、默认标记、版本时间、复制/删除。
2. 顶部操作栏：策略名称、保存、保存为默认、保存并运行。
3. 参数工作台：按分类分组展示指标。
4. 右侧或底部摘要：当前启用过滤数、评分项、风险项、候选上限、预计数据覆盖。
5. 最近运行解释：每条过滤影响、分项得分、缺失数据提示。

### 参数组 UI

每个分类是一段独立工作区，不做深层嵌套卡片：

- 组标题：图标 + 分类名 + 启用项数量。
- 指标行：名称、当前值/阈值、单位、用途、启用开关。
- 数值输入：固定宽度，右侧单位。
- 选择项：使用 segmented controls 或简洁菜单。
- 风险项：使用扣分输入和红色风险标识。
- 覆盖不足：显示小型 coverage chip，禁用硬筛选。

### 推荐阈值

每个指标可提供 2-3 个推荐值：

- 保守。
- 标准。
- 激进。

推荐值是辅助，不是隐藏模板。

### 不再出现

- 信号模式选择。
- 组合倍率。
- interaction terms。
- “平台突破模式 / 趋势共振模式”的运行入口。
- 让用户选择内部角色的下拉框。

## 后端改造

### 删除或降级旧服务

- `SignalModeService` 不再参与 bootstrap。
- `/api/signal-modes` 路由进入废弃期，前端不再调用。
- `signal_modes` 表可保留但不再读写。
- `strategy_interactions` 在 normalize 阶段清空或迁移 warning。

### 新模块

建议新增：

- `feature_service.py`：构建 feature_frame。
- `strategy_engine.py`：执行过滤、评分、风险和解释。
- `strategy_migration.py`：旧配置迁移为 V2。
- `indicator_registry.py`：继续作为指标元数据源，但删除 signal mode 模板职责。

### 分析服务

`AnalysisService.run()` 改成：

```py
strategy = normalize_strategy_config_v2(config)
frame = FeatureService(db).build(strategy)
candidates, funnel, explanation = StrategyEngine(strategy).run(frame)
```

不再在 `analysis_service.py` 内部按 `signal_mode` 写大型 if 分支。

## 数据覆盖与安全规则

- 可硬筛指标必须覆盖稳定，且缺失处理清晰。
- 事件类指标覆盖低时默认展示或评分，不默认过滤。
- 所有资金、龙虎榜、筹码指标必须带 `as_of_date`。
- 运行结果必须保存每个特征的数据来源和最新日期。
- 如果某个启用字段完全缺失，运行结果显示 warning，不静默忽略。

## 测试计划

后端：

- 旧策略迁移测试：确认低风险字段保留，高风险字段给 warning。
- interaction 删除测试：旧 `strategy_interactions` 不影响新分数。
- signal mode 删除测试：不同 `signal_mode` 输入不会改变新引擎分支。
- feature_frame 测试：Tushare moneyflow、limit、cyq、top、ths 数据正确进入特征。
- 策略执行测试：过滤、评分、风险、缺失处理、排序。
- 解释测试：候选保存分项分数和规则命中原因。

前端：

- 策略页不出现信号模式、组合倍率、interaction 文案。
- 指标按分类显示，移动端不横向溢出。
- 覆盖不足指标不能硬筛。
- 旧策略加载后显示迁移提示。
- 保存并运行 V2 策略。

端到端：

- 创建题材热度 + 量比 + RPS 的策略并运行。
- 创建资金净流入加权策略并运行。
- 创建龙虎榜展示/评分策略并运行。
- 创建筹码风险策略并运行。
- 旧自定义策略迁移后保存、运行、重载不丢关键阈值。

## 实施阶段

### 阶段一：去旧入口和配置迁移

- 前端移除组合倍率 UI。
- bootstrap 不再提供 signal modes。
- normalize 清空或忽略 `strategy_interactions`。
- 增加 V1 -> V2 迁移层。
- 保留旧字段值的迁移报告。

### 阶段二：feature_frame

- 抽出统一 feature_frame。
- 接入 daily_basic、stk_factor、moneyflow、limit_list_d、cyq、ths、top、market_environment。
- 为每个字段记录来源和日期。

### 阶段三：新策略引擎

- 实现过滤、评分、风险、解释。
- 移除 `signal_mode` 运行分支。
- 新候选结果保存分项得分和解释。

### 阶段四：策略页重做

- 按分类展示全部可用参数。
- 增加推荐阈值和覆盖状态。
- 增加迁移提示。
- 增加最近运行解释。

### 阶段五：清理旧代码

- 删除不再使用的 signal mode 管理 UI 和 API 调用。
- 删除 interaction 类型和测试。
- 更新 README 和部署说明。
- 保留数据库旧表，不做破坏性迁移。

## 验收标准

- 用户无法选择信号模式。
- 用户无法创建或编辑 interaction terms / 组合倍率。
- 旧 `strategy_interactions` 不再影响分析结果。
- 已有 Tushare 数据被转换为策略页可理解的参数。
- 题材、资金、事件、筹码至少能作为评分或展示进入结果。
- 低风险旧策略值能自动保留。
- 高风险旧逻辑不会被静默伪装成新规则。
- 运行结果能解释每个候选为什么留下、为什么得分、主要风险是什么。
- 本地改动、推送、云服务器 `git pull` + systemd restart 的部署流程不需要额外手工数据迁移。
