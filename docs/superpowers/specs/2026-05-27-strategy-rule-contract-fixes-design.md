# 策略规则契约与共振语义修复设计

日期：2026-05-27

## 背景

当前 `main` 分支已经完成了“特征驱动策略引擎”的大方向：旧 `signal_mode` 被迁移为 `feature_driven`，旧 `strategy_interactions` 会被丢弃，策略页也恢复了补充指标规则构建器。

但 GPT Pro 审查意见指出的核心问题成立：实现仍处在“旧参数墙 + 新规则构建器 + 显式共振乘数”的混合态。最大风险不是少几个指标，而是部分指标看起来可以筛选、加分或扣风险，但它们的执行字段、单位、覆盖率、缺失策略、事件语义和结果展示没有完全对齐。

本设计聚焦修复策略规则契约，不继续堆指标。目标是让每个可编辑项都满足：

- 用户知道它是什么、单位是什么、怎么生效。
- 前端不会展示后端无法可靠执行的动作。
- 后端不会静默忽略看似可执行的规则。
- 候选结果能解释过滤、加分、扣分、展示和共振的实际影响。

## 主要问题

### 1. 指标动作过度开放

`indicator_registry.py` 当前会给非事件、`analysis_ready=True` 的数据指标自动补 `filter` 动作。结果是主力净额、筹码胜率、中位成本、封单市值比、龙虎榜净额等字段即使原始用途只声明了 `score`、`risk` 或 `display`，也会在前端变成可硬筛。

这会让用户误以为所有 analysis-ready 字段都适合做硬过滤。实际上资金、筹码、事件类字段通常覆盖率更低、口径更依赖日期、横向可比性更弱，默认应该更保守。

### 2. 共振仍是乘数模型

旧 `strategy_interactions` 已经被移除，但新 `strategy_resonances` 又引入了“条件同时命中后乘总分”的模型。这个模型是显式的，不是隐藏 interaction，但仍然有三个问题：

- 共振条件重新填写阈值，和上方已有规则可能形成两套不同阈值。
- 多个共振连续相乘，会放大高基础分股票，排序解释变差。
- 设计文档已经明确倾向“加权评分，不再使用组合倍率”。

### 3. 事件与状态字段语义不严

`recent` 操作符目前按数字字段判断 `numeric <= window`。这适合“距最近涨停天数”“距龙虎榜天数”这类 days-since 字段，不适合 `limit_type` 这种字符串事件状态。

类似地，`macd_state` 注册为可执行指标，但分析帧里实际更明确的字段是 `macd_dif`、`macd_dea`、`trend_macd_dif_above_dea` 等。`overheat_risk` 注册为风险项，但如果没有独立分析字段，就不应该作为可编辑规则出现。

### 4. 绝对金额与绝对价格不适合直接横向筛股

主力净额、资金净流入、龙虎榜净额、机构净买额、游资净买额这些绝对金额对大市值股票天然更友好。中位成本 `cost_50pct` 是绝对价格，横向比较意义很弱。

这些字段可以展示，也可以在补充归一化指标后参与评分，但不应默认硬筛。

### 5. 只展示规则没有结果页承接

候选结果的 `metrics_json` 已经保存完整候选行，但候选表和展开面板没有按 `display` 规则动态展示这些字段。用户选择“只展示”后，页面没有明确告诉用户“这个字段已展示但不影响排序”。

### 6. 策略页仍像参数墙

运行参数默认全展开，平台、突破、趋势、随机指标、MACD、题材、输出等字段密度很高。兼容参数仍出现在指标注册里。对调参有帮助，但不利于判断“核心条件、高级参数、兼容迁移字段”的优先级。

## 目标

1. 移除数据指标的自动 `filter` 补全，所有动作必须显式声明。
2. 给指标注册增加可执行契约：是否可硬筛、执行字段、单位、推荐规则、覆盖/freshness 提示和 operator 约束。
3. 把共振从“独立条件 + 乘总分”改为“引用已有规则 + 固定加分 + 总上限”。
4. 禁止 `recent` 绑定非 days-since 字段。
5. 降级或拆分高风险指标：`macd_state`、`overheat_risk`、`cost_50pct`、`limit_event` 等。
6. 让 `display` 规则进入候选结果展示，并明确不影响排序。
7. 把策略页分成核心、补充规则、展示列、共振和高级/兼容设置。

## 非目标

- 不做公式编辑器、脚本语言或 Pine Script 类能力。
- 不引入自动交易、券商接入、登录权限。
- 不一次性补齐所有资金、事件、筹码新指标。
- 不推翻已有特征驱动分析帧。
- 不要求第一版就计算实时覆盖率分布；可以先预留元数据字段，再逐步接入真实覆盖统计。

## 指标契约

### 新增或收紧的元数据

在 `IndicatorDefinition` 中扩展或严格使用以下字段：

```ts
type IndicatorDefinition = {
  value_type: "number" | "money" | "percent" | "ratio" | "multiple" | "score" | "boolean" | "choice" | "event";
  unit: string;
  direction: "higher_better" | "lower_better" | "range_better" | "neutral" | "event";
  analysis_field?: string;
  data_status: "executable" | "display_only" | "planned" | "parameter";
  supported_actions: Array<"filter" | "score" | "risk" | "display">;
  supported_operators: string[];
  default_operator: string;
  hard_filter_allowed: boolean;
  min_coverage_for_filter?: number;
  freshness_required?: boolean;
  coverage_group?: string;
  operator_semantics?: "numeric" | "boolean" | "choice" | "event_state" | "days_since";
  recommended_rules?: RecommendedRule[];
};
```

规则：

- 不再因为 `analysis_ready=True` 自动补 `filter`。
- `filter` 只能在 `hard_filter_allowed=True` 时出现。
- `recent` 只能在 `operator_semantics="days_since"` 的指标上出现。
- `event_state` 字段只允许 `eq`、`neq`。
- `display_only` 指标只能出现在展示列/展示规则里。

### 第一轮指标口径调整

| 指标 | 调整 |
| --- | --- |
| `main_net_amount`、`net_mf_amount`、`large_net_amount`、`super_large_net_amount` | 默认 `score/display`，不默认 `filter`。后续新增金额/成交额、金额/流通市值、近 3/5 日累计后再考虑筛选。 |
| `top_list_net_amount`、`top_inst_net_buy`、`hot_money_net_amount` | 默认 `score/risk/display` 或 `display`，不默认硬筛。补“距上榜天数”和“净额/成交额”后再开放更强动作。 |
| `limit_event` | 拆分为事件状态和事件距离。当前 `limit_type` 只支持 `eq/neq`，不支持 `recent`。 |
| `limit_fd_mv_ratio` | 默认 `score/display`，硬筛需要覆盖率提示。 |
| `cyq_winner_rate` | 默认区间评分/风险，不默认硬筛。过高可作为风险。 |
| `cost_50pct` | 改为 `display` only。绝对价格不参与横向评分。 |
| `price_to_cost_50pct` | 明确为 `ratio` 或 `percent`，推荐区间评分，例如 `-5%` 到 `+15%`。 |
| `macd_state` | 拆成真实可执行布尔指标，或暂时降为展示/计划项。 |
| `overheat_risk` | 如果没有独立分析字段，先降为 `display_only` 或 `planned`；用近 5 日涨幅、近 10 日涨幅、距均线距离、换手过热等真实字段替代。 |
| `market_breadth` | 从个股补充规则中移出，进入市场环境模块。 |

## 后端设计

### 指标注册

修改 `indicator_registry.py`：

1. 删除 `_rule_builder_meta()` 中“非事件自动补 filter”的逻辑。
2. 为高风险指标显式设置 `supported_actions` 和 `hard_filter_allowed`。
3. 为事件字段区分 `operator_semantics`。
4. 为 `price_to_cost_50pct` 设置正确单位、类型和推荐区间。
5. 不再把全局市场环境指标提供给个股补充规则。

### 规则归一化与预检

新增规则预检函数，例如：

```py
validate_strategy_rules(strategy, indicators, frame_columns=None) -> RuleValidationResult
```

预检输出：

- `warnings`: 用户可读警告。
- `disabled_rule_ids`: 被禁用或降级的规则。
- `display_rule_fields`: 本次需要在候选结果展示的字段。

执行原则：

- 保存时做静态预检：动作不支持、operator 不支持、指标不可执行时给出 warning。
- 运行时做动态预检：分析帧没有字段时写入 run summary 和 funnel，不静默忽略。
- 对旧配置保持兼容，但不要把不合法动作重新变成可执行。

### 规则执行

`apply_strategy_filters()` 保持基础过滤、硬筛规则和候选排序职责，但补充：

- filter 规则只执行明确允许硬筛的指标。
- score/risk 规则在候选评分中产生明细。
- display 规则不影响筛选和排序，只进入候选展示字段。
- 每条规则记录命中、缺失和忽略原因。

候选 `metrics_json` 中增加结构化结果：

```json
{
  "strategy_rule_results": [
    {
      "rule_id": "rule-topic-heat",
      "indicator_id": "topic_heat",
      "action": "score",
      "matched": true,
      "value": 78.5,
      "adjustment": 8
    }
  ],
  "display_metrics": {
    "top_list_net_amount": 12000000,
    "price_to_cost_50pct": 0.08
  }
}
```

### 共振改造

把 `StrategyResonance` 从独立条件改成规则引用：

```ts
type StrategyResonance = {
  id: string;
  name: string;
  rule_ids: string[];
  bonus: number;
  enabled: boolean;
};
```

执行语义：

- 共振只能引用已有启用规则。
- 被引用规则都命中时，共振产生固定加分。
- 总共振加分设置上限，默认 `15` 分。
- 分数明细显示 `resonance_bonus`，不再显示 `resonance_multiplier`。
- 候选解释写成“命中共振：题材量能强确认，+8 分”。

迁移：

- 旧 `strategy_interactions` 继续丢弃。
- 旧 `strategy_resonances` 如果能精确匹配已有 `strategy_rules`，可迁移为 `rule_ids + bonus`。
- 无法精确匹配的旧共振禁用并写入迁移 warning，避免保留两套阈值。

## 前端设计

继续保持现有深色、紧凑、金融终端式视觉，不做营销式页面。

### 策略页结构

1. 核心股票池：最低股价、成交额、流通市值、市场范围、候选数量、排序。
2. 买点形态：平台突破、平台临界、趋势共振的核心条件。
3. 补充指标规则：资金、事件、筹码、题材等规则。
4. 展示列：用户选择结果页额外展示哪些字段。
5. 规则共振：选择已有规则组合，设置固定加分。
6. 高级参数：窗口、MACD 参数、随机指标、缺失处理。
7. 兼容/迁移详情：默认折叠，不参与日常调参。

### 补充指标规则

前端只展示后端声明支持的动作：

- 没有 `filter` 的指标不显示筛选按钮。
- `display_only` 指标只能加入展示列。
- 指标卡显示能力 chip：可筛选、可加分、可扣风险、仅展示、覆盖低、待接入。
- 不再用“字段尚未进入分析帧但允许保存”的体验作为正常路径。

### 共振 UI

修改 `StrategyResonanceBuilder`：

- 不再默认选前两个指标作为草稿。
- 空态提示用户先创建规则，再选择规则组成共振。
- 共振行展示“规则 A + 规则 B => +8 分”。
- 不能在共振里编辑阈值，只能跳转或定位到原规则。
- 移除乘数按钮和 `x1.10` 文案。

### 候选结果

候选表保留核心列，不无限增加横向宽度。

展开详情中增加：

- 自定义规则命中明细。
- 共振加分明细。
- 展示字段列表，标明“不参与排序”。
- 被忽略规则或缺失字段 warning。

## 测试计划

### 后端测试

新增或修改：

- `backend/tests/test_indicator_registry.py`
  - 非事件 analysis-ready 指标不会自动获得 `filter`。
  - `cost_50pct` 只能展示。
  - `limit_event` 不支持 `recent`。
  - `market_breadth` 不进入个股规则候选。
  - `macd_state` 被拆分或降级。

- `backend/tests/test_strategy_service.py`
  - 旧乘数共振迁移为规则引用式共振或被禁用并产生 warning。
  - 新共振结构只接受 `rule_ids` 和 `bonus`。
  - 旧 `strategy_interactions` 仍被丢弃。

- `backend/tests/test_indicators.py`
  - `main_net_amount` 作为 filter 不执行，并产生 warning。
  - `recent` 绑定字符串事件字段会被拒绝或忽略并产生 warning。
  - 共振固定加分，不乘总分，多共振受上限约束。
  - display 规则不改变 `signal_score`。

- `backend/tests/test_analysis_frame.py`
  - 展示字段进入 `display_metrics`。
  - 规则命中结果进入 `strategy_rule_results`。

### 前端验证

- `npm --prefix frontend run build` 通过。
- 补充规则中主力净额不显示“筛选”按钮。
- 中位成本只能作为展示字段。
- 共振空态不自动填指标。
- 共振只能选择已有规则，并显示固定加分。
- 候选展开详情能看到展示字段和规则影响。

## 分阶段实施

### Phase 1: 收紧指标契约

优先改 registry 和测试，确保前端不会再展示假可执行动作。这一阶段不改变评分主干。

### Phase 2: 共振语义改造

把 multiplier 改成 rule reference + bonus。迁移旧共振配置，更新候选评分明细和原因文案。

### Phase 3: 结果解释与展示列

把 display 规则真正接到候选详情中，补 `strategy_rule_results` 和 `display_metrics`。

### Phase 4: 策略页分层

将运行参数改成核心/高级/兼容分层，压低参数墙感。这个阶段主要是前端结构和 CSS 调整。

### Phase 5: 补归一化指标

在契约稳定后再新增：

- 主力净额 / 成交额。
- 主力净额 / 流通市值。
- 近 3/5 日主力净额。
- 距最近涨停天数。
- 距龙虎榜天数。
- 龙虎榜净额 / 成交额。
- 筹码成本区间宽度。
- 上方压力距离。

## 验收标准

1. 用户不能在 UI 里给不适合硬筛的指标设置 filter。
2. 后端不会静默忽略用户以为已生效的规则。
3. 共振不再乘总分，也不再重填一套阈值。
4. 候选结果能说明每条规则和共振如何影响分数。
5. 只展示字段能在结果详情中看到，并明确不影响排序。
6. 现有系统策略和旧自定义策略可迁移，不会因为字段收紧直接报错中断分析。

## 部署与回滚

部署仍沿用当前工作流：

1. 本地实现、测试、提交并推送 `main`。
2. 云服务器 `git pull`。
3. 安装依赖并构建前端。
4. 运行 `python scripts/init_db.py`。
5. 重启 `ashare-signal` systemd 服务。

本次主要是代码和配置 JSON 语义调整，不需要破坏性数据库迁移。回滚代码即可恢复旧行为。旧策略中无法迁移的乘数共振只应以 migration warning 形式保留，不删除用户原始配置记录。
