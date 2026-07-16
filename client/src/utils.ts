let idCounter = 0;

export function makeId(prefix = "item"): string {
  idCounter += 1;
  return `${prefix}_${Date.now()}_${idCounter}`;
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export function formatElapsed(value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "";
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  return `${value.toFixed(1)}s`;
}

export function toolPreview(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const data = args as Record<string, unknown>;
  const keys = ["command", "file_path", "path", "pattern", "query", "team_name"];
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

export function stringifyJson(value: unknown): string {
  if (value === undefined || value === null) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
