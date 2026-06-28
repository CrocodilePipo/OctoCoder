// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import React from "react";
import { Box, Text } from "ink";
import chalk from "chalk";
import { marked } from "marked";
import { markedTerminal } from "marked-terminal";
import { brand, symbols } from "./styles.js";

chalk.level = 3;
marked.use(markedTerminal({ showSectionPrefix: false }));

function renderMarkdown(text: string): string {
  try {
    return marked.parse(text) as string;
  } catch {
    return text;
  }
}

export interface ToolSummaryItem {
  toolName: string;
  argsSummary: string;
  output: string;
  isError: boolean;
  elapsed: number;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | "thinking" | "tool_use" | "tool_result" | "turn_summary";
  content: string;
  toolName?: string;
  argsSummary?: string;
  isError?: boolean;
  elapsed?: number;
  // turn_summary fields
  thinkingDuration?: number;
  toolSummary?: ToolSummaryItem[];
}

interface Props {
  messages: ChatMessage[];
  streamingText?: string;
  expanded?: boolean;
}

export function ChatView({ messages, streamingText, expanded = false }: Props) {
  return (
    <Box flexDirection="column" paddingLeft={1}>
      {messages.map((msg, i) => (
        <MessageBlock key={i} message={msg} expanded={expanded} />
      ))}
      {streamingText !== undefined && streamingText !== "" && (
        <Box>
          <Text>
            {brand.assistant(`${symbols.dot} `)}
            {renderMarkdown(streamingText)}
          </Text>
        </Box>
      )}
    </Box>
  );
}

/**
 * CommittedMessage renders a single finalized message for use inside Ink's
 * <Static> component. Once rendered, Static never re-renders it, eliminating
 * flicker from the scrollback history.
 */
export function CommittedMessage({ message, expanded = false }: { message: ChatMessage; expanded?: boolean }) {
  return (
    <Box paddingLeft={1}>
      <MessageBlock message={message} expanded={expanded} />
    </Box>
  );
}

/**
 * Build a compact human-readable summary line for a turn, e.g.:
 *   "Thought for 4s, read 2 files, ran 1 command"
 */
function buildTurnSummaryText(thinkingDuration: number | undefined, tools: ToolSummaryItem[]): string {
  const parts: string[] = [];

  if (thinkingDuration !== undefined && thinkingDuration >= 1) {
    parts.push(`Thought for ${Math.round(thinkingDuration)}s`);
  }

  if (tools.length > 0) {
    // Categorize tools by type for a natural summary.
    const counts: Record<string, number> = {};
    for (const t of tools) {
      const name = t.toolName;
      if (name === "ReadFile") {
        counts["read"] = (counts["read"] ?? 0) + 1;
      } else if (name === "WriteFile") {
        counts["wrote"] = (counts["wrote"] ?? 0) + 1;
      } else if (name === "EditFile") {
        counts["edited"] = (counts["edited"] ?? 0) + 1;
      } else if (name === "Bash") {
        counts["ran"] = (counts["ran"] ?? 0) + 1;
      } else if (name === "Glob") {
        counts["globbed"] = (counts["globbed"] ?? 0) + 1;
      } else if (name === "Grep") {
        counts["searched"] = (counts["searched"] ?? 0) + 1;
      } else {
        counts["used"] = (counts["used"] ?? 0) + 1;
      }
    }

    const labels: Record<string, (n: number) => string> = {
      read: (n) => `read ${n} file${n > 1 ? "s" : ""}`,
      wrote: (n) => `wrote ${n} file${n > 1 ? "s" : ""}`,
      edited: (n) => `edited ${n} file${n > 1 ? "s" : ""}`,
      ran: (n) => `ran ${n} command${n > 1 ? "s" : ""}`,
      globbed: (n) => `globbed ${n} pattern${n > 1 ? "s" : ""}`,
      searched: (n) => `searched ${n} pattern${n > 1 ? "s" : ""}`,
      used: (n) => `used ${n} tool${n > 1 ? "s" : ""}`,
    };

    for (const [key, count] of Object.entries(counts)) {
      parts.push(labels[key](count));
    }
  }

  if (parts.length === 0) return "";
  return parts.join(", ");
}

function TurnSummaryBlock({ message, expanded }: { message: ChatMessage; expanded: boolean }) {
  const { content: thinkingText, thinkingDuration, toolSummary = [] } = message;
  const summaryText = buildTurnSummaryText(thinkingDuration, toolSummary);

  if (!summaryText) return null;

  if (!expanded) {
    return (
      <Box marginBottom={0}>
        <Text dimColor>
          {"  "}{summaryText}
        </Text>
      </Box>
    );
  }

  // Expanded: full thinking + individual tool results
  return (
    <Box flexDirection="column" marginBottom={0}>
      <Text dimColor>{summaryText}</Text>
      {thinkingText ? (
        <Box marginBottom={0}>
          <Text dimColor>
            {brand.thinking(`${symbols.thinking} `)}
            {thinkingText}
          </Text>
        </Box>
      ) : null}
      {toolSummary.map((t, i) => {
        const icon = t.isError ? brand.error(symbols.error) : brand.success(symbols.success);
        const timeStr = t.elapsed !== undefined ? ` (${t.elapsed.toFixed(1)}s)` : "";
        return (
          <Box key={i} flexDirection="column" marginBottom={0}>
            <Text>
              {icon} {brand.tool(t.toolName)}
              {t.argsSummary ? <Text dimColor> {t.argsSummary}</Text> : null}
              <Text dimColor>{timeStr}</Text>
            </Text>
            {t.output ? (
              <Box paddingLeft={2}>
                <Text dimColor>
                  {t.output.length > 500
                    ? t.output.slice(0, 500) + "..."
                    : t.output}
                </Text>
              </Box>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

function MessageBlock({ message, expanded }: { message: ChatMessage; expanded: boolean }) {
  switch (message.role) {
    case "user":
      return (
        <Box marginBottom={0}>
          <Text>
            {brand.primary(`${symbols.prompt} `)}
            {message.content}
          </Text>
        </Box>
      );

    case "assistant":
      return (
        <Box marginBottom={0}>
          <Text>{renderMarkdown(message.content)}</Text>
        </Box>
      );

    case "thinking":
      return (
        <Box marginBottom={0}>
          <Text dimColor>
            {brand.thinking(`${symbols.thinking} `)}
            {message.content.length > 200
              ? message.content.slice(0, 200) + "..."
              : message.content}
          </Text>
        </Box>
      );

    case "tool_use":
      return (
        <Box marginBottom={0}>
          <Text>
            <Text color="magenta">●</Text>
            {" "}{brand.tool(message.toolName ?? "tool")}
            {message.argsSummary ? <Text dimColor> {message.argsSummary}</Text> : null}
          </Text>
        </Box>
      );

    case "tool_result": {
      const icon = message.isError ? brand.error(symbols.error) : brand.success(symbols.success);
      const timeStr = message.elapsed !== undefined ? ` (${message.elapsed.toFixed(1)}s)` : "";
      return (
        <Box flexDirection="column" marginBottom={0}>
          <Text>
            {icon} {brand.tool(message.toolName ?? "tool")}
            {message.argsSummary ? <Text dimColor> {message.argsSummary}</Text> : null}
            <Text dimColor>{timeStr}</Text>
          </Text>
          {message.content && (
            <Box paddingLeft={2}>
              <Text dimColor>
                {!expanded && message.content.length > 500
                  ? message.content.slice(0, 500) + "…  (ctrl+o to expand)"
                  : message.content}
              </Text>
            </Box>
          )}
        </Box>
      );
    }

    case "turn_summary":
      return <TurnSummaryBlock message={message} expanded={expanded} />;

    case "system":
      return (
        <Box marginBottom={0}>
          <Text dimColor>{message.content}</Text>
        </Box>
      );

    default:
      return null;
  }
}
