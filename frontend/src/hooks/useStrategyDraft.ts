import { create } from 'zustand';
import type { StrategyConfig, StrategyRule, StrategyResonance } from '../types';
import { composeStrategyConfig } from '../utils/strategy';

type StrategyDraftState = {
  name: string;
  config: StrategyConfig | null;
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  initialized: boolean;
  setDraft: (name: string, config: StrategyConfig | null) => void;
  setName: (name: string) => void;
  setRules: (rules: StrategyRule[]) => void;
  setResonances: (resonances: StrategyResonance[]) => void;
};

export const useStrategyDraft = create<StrategyDraftState>((set) => ({
  name: '我的 Scanner',
  config: null,
  rules: [],
  resonances: [],
  initialized: false,
  setDraft: (name, config) =>
    set({
      name,
      config,
      rules: Array.isArray(config?.strategy_rules) ? config.strategy_rules : [],
      resonances: Array.isArray(config?.strategy_resonances) ? config.strategy_resonances : [],
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
}));
