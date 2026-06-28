// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type { Message } from "../conversation/conversation.js";
import { ContentReplacementState } from "./state.js";

const SINGLE_RESULT_LIMIT = 50000;
const MESSAGE_AGGREGATE_LIMIT = 200000;
function spillDir(workDir: string): string {
  return join(workDir, ".mewcode", "tool_results");
}

function writeSpill(workDir: string, toolUseId: string, content: string): string {
  const dir = spillDir(workDir);
  mkdirSync(dir, { recursive: true });
  const path = join(dir, toolUseId);
  try {
    writeFileSync(path, content, { encoding: "utf-8", flag: "wx" });
  } catch (e: any) {
    if (e.code !== "EEXIST") throw e;
  }
  return path;
}

const PREVIEW_CHARS = 2000;

function buildSpillPreview(content: string, spillPath: string): string {
  const sizeKB = Math.floor(content.length / 1024);
  const preview = content.slice(0, PREVIEW_CHARS);
  const hasMore = content.length > PREVIEW_CHARS;
  let msg = '<persisted-output>\n';
  msg += `输出太大（${sizeKB}KB），完整内容已保存到：\n${spillPath}\n\n`;
  msg += `预览（前 2KB）：\n${preview}`;
  if (hasMore) msg += '\n...';
  msg += '\n</persisted-output>';
  return msg;
}

export function applyBudget(
  messages: Message[],
  workDir: string,
  state: ContentReplacementState
): Message[] {
  const result: Message[] = [];

  for (let mi = 0; mi < messages.length; mi++) {
    const msg = { ...messages[mi] };

    if (msg.toolResults && msg.toolResults.length > 0) {
      const newResults = msg.toolResults.map((tr) => {
        // 已有替换决策，直接回放以保持 prompt-cache 稳定
        const existing = state.getReplacement(tr.toolUseId);
        if (existing !== undefined) {
          return { ...tr, content: existing };
        }

        let content = tr.content;

        // Pass 1: 单条结果超限 → 溢出到磁盘
        if (content.length > SINGLE_RESULT_LIMIT) {
          const spillPath = writeSpill(workDir, tr.toolUseId, content);
          content = buildSpillPreview(content, spillPath);
          state.record(tr.toolUseId, tr.content, content);
        }

        return { ...tr, content };
      });

      // Pass 2: 单消息聚合超限 → 溢出最大的结果
      let totalLen = newResults.reduce((sum, r) => sum + r.content.length, 0);
      if (totalLen > MESSAGE_AGGREGATE_LIMIT) {
        const sorted = [...newResults].sort(
          (a, b) => b.content.length - a.content.length
        );
        for (const r of sorted) {
          if (totalLen <= MESSAGE_AGGREGATE_LIMIT) break;
          if (r.content.length > PREVIEW_CHARS) {
            const before = r.content;
            const spillPath = writeSpill(workDir, r.toolUseId, before);
            const replacement = buildSpillPreview(before, spillPath);
            totalLen = totalLen - before.length + replacement.length;
            r.content = replacement;
            state.record(r.toolUseId, before, replacement);
          }
        }
      }

      msg.toolResults = newResults;
    }

    result.push(msg);
  }

  return result;
}

