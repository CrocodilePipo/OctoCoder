// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import type { LLMClient } from "../llm/client.js";
import { ConversationManager } from "../conversation/conversation.js";
import { MemoryManager } from "./manager.js";

/**
 * MemoryExtractor 实现后台记忆提取子代理。
 *
 * 提取合并策略（对齐 Go 版 Extractor）：
 * - inProgress 标志防止并发提取：一次只允许一个提取运行
 * - pendingContext 队列：如果提取进行中又收到新请求，暂存为尾部运行
 * - 当前提取完成后自动执行尾部运行（coalescing）
 */
export class MemoryExtractor {
  private client: LLMClient;
  private workDir: string;
  /** 当前是否有提取正在进行 */
  private inProgress = false;
  /** 是否有待处理的尾部提取请求 */
  private pendingContext: string | null = null;

  constructor(client: LLMClient, workDir: string) {
    this.client = client;
    this.workDir = workDir;
  }

  /**
   * 提取记忆的入口方法。支持合并策略：
   * - 如果当前已有提取在进行，将请求暂存为 pendingContext
   * - 当前提取完成后自动执行暂存的请求
   */
  async extract(conversationSummary: string): Promise<string[]> {
    // 合并策略：如果已有提取在进行中，暂存请求以待后续执行
    if (this.inProgress) {
      this.pendingContext = conversationSummary;
      return [];
    }

    return this.runExtraction(conversationSummary);
  }

  /** 实际执行提取逻辑，带 inProgress 互斥和 trailing run 支持 */
  private async runExtraction(conversationSummary: string): Promise<string[]> {
    this.inProgress = true;
    let result: string[] = [];

    try {
      result = await this.doExtract(conversationSummary);
    } finally {
      this.inProgress = false;

      // 如果有暂存的尾部提取请求，取出并执行
      const pending = this.pendingContext;
      this.pendingContext = null;
      if (pending !== null) {
        // 尾部运行：使用最新的上下文重新执行
        const trailingResult = await this.runExtraction(pending);
        result = [...result, ...trailingResult];
      }
    }

    return result;
  }

  /** 核心提取逻辑：调用 LLM 分析对话并提取值得保存的记忆 */
  private async doExtract(conversationSummary: string): Promise<string[]> {
    const conv = new ConversationManager();
    conv.addUserMessage(
      "Based on the following conversation, extract any memories worth saving.\n" +
        "For each memory, output it in this format:\n" +
        "MEMORY_NAME: <kebab-case-name>\n" +
        "MEMORY_TYPE: <user|feedback|project|reference>\n" +
        "MEMORY_DESC: <one-line description>\n" +
        "MEMORY_BODY: <content>\n" +
        "---\n\n" +
        "If no memories are worth saving, output NONE.\n\n" +
        "Conversation:\n" +
        conversationSummary
    );

    let response = "";
    const stream = this.client.stream(conv, []);
    for await (const event of stream) {
      if (event.type === "text_delta") {
        response += event.text;
      }
    }

    if (response.trim() === "NONE" || !response.includes("MEMORY_NAME:")) {
      return [];
    }

    const userDir = join(homedir(), ".mewcode", "memory");
    const projectDir = join(this.workDir, ".mewcode", "memory");
    const saved: string[] = [];

    const blocks = response.split("---").filter((b) => b.includes("MEMORY_NAME:"));
    for (const block of blocks) {
      const name = extractField(block, "MEMORY_NAME");
      const type = extractField(block, "MEMORY_TYPE") || "reference";
      const desc = extractField(block, "MEMORY_DESC");
      const body = extractField(block, "MEMORY_BODY");

      if (!name || !body) continue;

      // 双路路由：project/reference 存项目目录，user/feedback 存用户全局目录
      const dir = type === "project" || type === "reference" ? projectDir : userDir;
      mkdirSync(dir, { recursive: true });

      // type 字段放在顶层（跨语言兼容格式，与 Go 版一致）
      const content =
        `---\nname: ${name}\ndescription: ${desc}\ntype: ${type}\n---\n\n${body}\n`;

      writeFileSync(join(dir, `${name}.md`), content, "utf-8");
      saved.push(name);
    }

    // 写入新记忆后重建 MEMORY.md 索引
    if (saved.length > 0) {
      const mgr = new MemoryManager(this.workDir);
      mgr.rebuildIndex();
    }

    return saved;
  }
}

function extractField(block: string, field: string): string {
  const regex = new RegExp(`${field}:\\s*(.+?)(?:\\n|$)`);
  const match = block.match(regex);
  return match?.[1]?.trim() ?? "";
}
