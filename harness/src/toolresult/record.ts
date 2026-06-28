// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { ContentReplacementState } from "./state.js";

interface DecisionRecord {
  toolUseId: string;
  action: string;
  timestamp: string;
}

export function persistDecisions(state: ContentReplacementState): void {
  const dir = join(homedir(), ".mewcode");
  mkdirSync(dir, { recursive: true });
  const filePath = join(dir, "toolresult.jsonl");

  const record: DecisionRecord = {
    toolUseId: "batch",
    action: `recorded ${state.size()} decisions`,
    timestamp: new Date().toISOString(),
  };

  writeFileSync(filePath, JSON.stringify(record) + "\n", {
    flag: "a",
    encoding: "utf-8",
  });
}
