/**
 * Auto-correct system for common typos and text replacements.
 */

export interface AutoCorrectRule {
  from: string;
  to: string;
  enabled: boolean;
}

// Default auto-correct rules for Korean and common symbols
const DEFAULT_RULES: AutoCorrectRule[] = [
  // Common Korean typos
  { from: "ㅇㅇ", to: "응", enabled: true },
  { from: "ㄴㄴ", to: "노노", enabled: true },
  { from: "ㅎㅎ", to: "하하", enabled: true },
  { from: "ㄱㄱ", to: "고고", enabled: true },
  { from: "ㅋㅋ", to: "크크", enabled: false },

  // Common symbol replacements
  { from: "(c)", to: "©", enabled: true },
  { from: "(C)", to: "©", enabled: true },
  { from: "(r)", to: "®", enabled: true },
  { from: "(R)", to: "®", enabled: true },
  { from: "(tm)", to: "™", enabled: true },
  { from: "(TM)", to: "™", enabled: true },
  { from: "...", to: "…", enabled: true },
  { from: "->", to: "→", enabled: true },
  { from: "<-", to: "←", enabled: true },
  { from: "<->", to: "↔", enabled: true },
  { from: "=>", to: "⇒", enabled: true },
  { from: "<=", to: "⇐", enabled: true },
  { from: "1/2", to: "½", enabled: true },
  { from: "1/4", to: "¼", enabled: true },
  { from: "3/4", to: "¾", enabled: true },
  { from: "+-", to: "±", enabled: true },
  { from: "!=", to: "≠", enabled: true },
  { from: ">=", to: "≥", enabled: true },
  { from: "<=", to: "≤", enabled: true },

  // Common text expansions
  { from: "btw", to: "by the way", enabled: false },
  { from: "fyi", to: "for your information", enabled: false },
  { from: "asap", to: "as soon as possible", enabled: false },
];

const STORAGE_KEY = "hwpx-autocorrect-rules";

export class AutoCorrectManager {
  private rules: AutoCorrectRule[] = [];
  private enabled: boolean = true;

  constructor() {
    this.loadRules();
  }

  loadRules(): void {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.rules = parsed.rules ?? DEFAULT_RULES;
        this.enabled = parsed.enabled ?? true;
      } else {
        this.rules = [...DEFAULT_RULES];
        this.enabled = true;
      }
    } catch {
      this.rules = [...DEFAULT_RULES];
      this.enabled = true;
    }
  }

  saveRules(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        rules: this.rules,
        enabled: this.enabled,
      }));
    } catch (e) {
      console.error("Failed to save autocorrect rules:", e);
    }
  }

  getRules(): AutoCorrectRule[] {
    return [...this.rules];
  }

  setRules(rules: AutoCorrectRule[]): void {
    this.rules = [...rules];
    this.saveRules();
  }

  addRule(from: string, to: string): void {
    const existing = this.rules.find((r) => r.from === from);
    if (existing) {
      existing.to = to;
      existing.enabled = true;
    } else {
      this.rules.push({ from, to, enabled: true });
    }
    this.saveRules();
  }

  removeRule(from: string): void {
    this.rules = this.rules.filter((r) => r.from !== from);
    this.saveRules();
  }

  toggleRule(from: string): void {
    const rule = this.rules.find((r) => r.from === from);
    if (rule) {
      rule.enabled = !rule.enabled;
      this.saveRules();
    }
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    this.saveRules();
  }

  /**
   * Apply auto-correct to the given text.
   * Returns the corrected text and whether any corrections were made.
   */
  apply(text: string): { text: string; corrected: boolean } {
    if (!this.enabled) {
      return { text, corrected: false };
    }

    let result = text;
    let corrected = false;

    for (const rule of this.rules) {
      if (!rule.enabled) continue;
      if (result.includes(rule.from)) {
        result = result.split(rule.from).join(rule.to);
        corrected = true;
      }
    }

    return { text: result, corrected };
  }

  /**
   * Check if the text ends with a pattern that should trigger auto-correct.
   * Used for real-time correction as user types.
   */
  checkEndOfText(text: string): { replacement: string; length: number } | null {
    if (!this.enabled) return null;

    for (const rule of this.rules) {
      if (!rule.enabled) continue;
      if (text.endsWith(rule.from)) {
        return {
          replacement: rule.to,
          length: rule.from.length,
        };
      }
    }

    return null;
  }

  resetToDefaults(): void {
    this.rules = [...DEFAULT_RULES];
    this.enabled = true;
    this.saveRules();
  }
}

// Singleton instance
export const autoCorrectManager = new AutoCorrectManager();
