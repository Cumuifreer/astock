import { create } from 'zustand';
import type { StrategyConfig, StrategyRule, StrategyResonance } from '../types';
import { composeStrategyConfig } from '../utils/strategy';

type StrategyDraftState = {
  presetId: string | null;
  name: string;
  config: StrategyConfig | null;
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  isSystem: boolean;
  isDefault: boolean;
  initialized: boolean;
  setDraft: (draft: { presetId?: string | null; name: string; config: StrategyConfig | null; isSystem?: boolean; isDefault?: boolean }) => void;
  setName: (name: string) => void;
  setRules: (rules: StrategyRule[]) => void;
  setResonances: (resonances: StrategyResonance[]) => void;
  patchConfig: (patch: Partial<StrategyConfig>) => void;
};

export const useStrategyDraft = create<StrategyDraftState>((set) => ({
  presetId: null,
  name: '未命名策略',
  config: null,
  rules: [],
  resonances: [],
  isSystem: false,
  isDefault: false,
  initialized: false,
  setDraft: ({ presetId = null, name, config, isSystem = false, isDefault = false }) =>
    set({
      presetId,
      name,
      config,
      rules: Array.isArray(config?.strategy_rules) ? config.strategy_rules : [],
      resonances: Array.isArray(config?.strategy_resonances) ? config.strategy_resonances : [],
      isSystem,
      isDefault,
      initialized: Boolean(config),
    }),
  setName: (name) => set({ name }),
  setRules: (rules) =>
    set((state) => ({
      rules,
      config: state.config ? composeStrategyConfig(state.config, rules, state.resonances) : state.config,
    })),
  setResonances: (resonances) =>
    set((state) => ({
      resonances,
      config: state.config ? composeStrategyConfig(state.config, state.rules, resonances) : state.config,
    })),
  patchConfig: (patch) =>
    set((state) => {
      if (!state.config) return {};
      const nextConfig = { ...state.config, ...patch };
      return {
        config: composeStrategyConfig(nextConfig, state.rules, state.resonances),
      };
    }),
}));
