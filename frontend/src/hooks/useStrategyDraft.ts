import { create } from 'zustand';
import type { StrategyConfig, StrategyRule, StrategyResonance } from '../types';

type StrategyDraftState = {
  name: string;
  config: StrategyConfig | null;
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  setDraft: (name: string, config: StrategyConfig | null) => void;
  setRules: (rules: StrategyRule[]) => void;
  setResonances: (resonances: StrategyResonance[]) => void;
};

export const useStrategyDraft = create<StrategyDraftState>((set) => ({
  name: '我的 Scanner',
  config: null,
  rules: [],
  resonances: [],
  setDraft: (name, config) =>
    set({
      name,
      config,
      rules: Array.isArray(config?.strategy_rules) ? config.strategy_rules : [],
      resonances: Array.isArray(config?.strategy_resonances) ? config.strategy_resonances : [],
    }),
  setRules: (rules) => set({ rules }),
  setResonances: (resonances) => set({ resonances }),
}));
