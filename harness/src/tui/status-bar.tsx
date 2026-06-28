// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import React from "react";
import { Box, Text } from "ink";
import { brand, symbols } from "./styles.js";

interface Props {
  model: string;
  mode?: string;
  inputTokens?: number;
  outputTokens?: number;
}

export function StatusBar({ model, mode, inputTokens = 0, outputTokens = 0 }: Props) {
  const parts: string[] = [];
  if (mode) parts.push(mode);
  if (inputTokens > 0) parts.push(`${formatTokens(inputTokens)}↓ ${formatTokens(outputTokens)}↑`);

  if (parts.length === 0) return null;

  return (
    <Box paddingLeft={1} paddingTop={0} paddingBottom={0}>
      <Text dimColor>
        {parts.map((p, i) => (i > 0 ? ` ${symbols.dot} ` : `${symbols.dot} `) + p).join("")}
      </Text>
    </Box>
  );
}

function formatTokens(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
