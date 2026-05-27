# Unified Strategy Rule Workspace Design

**Goal:** Merge the strategy rule and resonance editing experience into one workspace so users treat resonance as a grouping of existing positive rules, not as a second condition system.

**Design:**
- Replace the two adjacent top-level sections with one `StrategyRuleWorkspace`.
- Keep backend data contracts unchanged: `strategy_rules` stores executable conditions, `strategy_resonances` stores references to eligible rule ids.
- Show resonance creation inside the rule workspace, using selectable rule chips from enabled `filter` and `score` rules.
- Remove blank resonance draft selects. If fewer than two eligible rules exist, show a compact empty state in the same workspace.
- Add a small resonance badge to eligible rule cards so users can see which rules can be grouped and how many groups already use them.
- Preserve legacy unmatched resonance recovery cards.

**Acceptance Criteria:**
- The strategy editor renders one rules/resonance workspace instead of separate rule and resonance sections.
- Draft resonance creation uses existing rule chips, not empty select boxes.
- Risk and display rules cannot be selected for positive resonance.
- Existing resonance edit/recovery behavior remains available.
- Frontend build passes.
