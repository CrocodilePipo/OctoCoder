// 来源：公众号@小林coding
// 后端八股网站：xiaolincoding.com
// Agent网站：xiaolinnote.com
// 简历模版：jianli.xiaolinnote.com

import React, { useState, useCallback, useRef } from "react";
import { Box, Text, useInput } from "ink";
import { brand, symbols } from "./styles.js";
import type { Question, AskAnswers } from "../tools/ask-user.js";

interface Props {
  questions: Question[];
  onComplete: (answers: AskAnswers) => void;
}

const OTHER = "Other (type your own)";

// Per-question UI state preserved across tab switches.
interface QuestionState {
  cursor: number;
  selected: Set<number>;
  otherText: string;
  otherMode: boolean;
  /** The committed answer string, undefined until user picks one. */
  answer: string | undefined;
}

function initState(): QuestionState {
  return { cursor: 0, selected: new Set(), otherText: "", otherMode: false, answer: undefined };
}

export function AskUserDialog({ questions, onComplete }: Props) {
  // Tab index: 0..questions.length-1 = question tabs, questions.length = Submit tab
  const [currentTab, setCurrentTab] = useState(0);
  const [states, setStates] = useState<QuestionState[]>(() => questions.map(() => initState()));

  // Ref keeps currentTab fresh for callbacks that outlive a render cycle.
  const currentTabRef = useRef(currentTab);
  currentTabRef.current = currentTab;

  const totalTabs = questions.length + 1; // +1 for Submit
  const isSubmitTab = currentTab === questions.length;
  const q = isSubmitTab ? undefined : questions[currentTab];
  const qs = isSubmitTab ? undefined : states[currentTab];

  // Whether all questions have an answer (enables Submit).
  const allAnswered = states.every((s) => s.answer !== undefined);

  // Helpers to update per-question state immutably.
  const updateCurrent = useCallback(
    (updater: (prev: QuestionState) => QuestionState) => {
      setStates((prev) => {
        const idx = currentTabRef.current;
        const next = [...prev];
        next[idx] = updater(next[idx]);
        return next;
      });
    },
    [],
  );

  const commitAnswer = useCallback(
    (answer: string) => {
      updateCurrent((s) => ({ ...s, answer, otherMode: false }));
    },
    [updateCurrent],
  );

  const switchTab = useCallback(
    (delta: number) => {
      setCurrentTab((t) => {
        let next = t + delta;
        if (next < 0) next = totalTabs - 1;
        if (next >= totalTabs) next = 0;
        return next;
      });
    },
    [totalTabs],
  );

  useInput((input, key) => {
    // ------ other-text typing mode (scoped to the current question) ------
    if (!isSubmitTab && qs?.otherMode) {
      if (key.return) {
        commitAnswer(qs.otherText.trim() || "(no answer)");
      } else if (key.backspace || key.delete) {
        updateCurrent((s) => ({ ...s, otherText: s.otherText.slice(0, -1) }));
      } else if (key.escape) {
        updateCurrent((s) => ({ ...s, otherMode: false }));
      } else if (input && !key.ctrl && !key.meta) {
        updateCurrent((s) => ({ ...s, otherText: s.otherText + input }));
      }
      return;
    }

    // ------ global: escape cancels entire dialog ------
    if (key.escape) {
      onComplete({});
      return;
    }

    // ------ tab navigation: left/right arrows, Tab / Shift+Tab ------
    if (key.leftArrow) {
      switchTab(-1);
      return;
    }
    if (key.rightArrow) {
      switchTab(1);
      return;
    }
    if (key.tab) {
      switchTab(key.shift ? -1 : 1);
      return;
    }

    // ------ Submit tab ------
    if (isSubmitTab) {
      if (key.return && allAnswered) {
        const answers: AskAnswers = {};
        for (let i = 0; i < questions.length; i++) {
          answers[questions[i].question] = states[i].answer!;
        }
        onComplete(answers);
      }
      return;
    }

    // ------ Question tab: up/down, space, enter ------
    if (!q || !qs) return;
    const rows = [...q.options.map((o) => o.label), OTHER];

    if (key.upArrow) {
      updateCurrent((s) => ({ ...s, cursor: s.cursor > 0 ? s.cursor - 1 : rows.length - 1 }));
    } else if (key.downArrow) {
      updateCurrent((s) => ({ ...s, cursor: s.cursor < rows.length - 1 ? s.cursor + 1 : 0 }));
    } else if (input === " " && q.multiSelect && qs.cursor < q.options.length) {
      updateCurrent((s) => {
        const n = new Set(s.selected);
        if (n.has(s.cursor)) n.delete(s.cursor);
        else n.add(s.cursor);
        return { ...s, selected: n };
      });
    } else if (key.return) {
      if (qs.cursor === rows.length - 1) {
        updateCurrent((s) => ({ ...s, otherMode: true }));
        return;
      }
      if (q.multiSelect && qs.selected.size > 0) {
        const answer = [...qs.selected]
          .sort((a, b) => a - b)
          .map((i) => q.options[i].label)
          .join(", ");
        commitAnswer(answer);
      } else {
        commitAnswer(q.options[qs.cursor]?.label ?? "(unknown)");
      }
    }
  });

  // ===================== Render =====================

  const renderTabBar = () => {
    const tabs: React.ReactNode[] = [];

    tabs.push(
      <Text key="left-arrow" dimColor>
        {"  "}
        {symbols.arrow === "→" ? "←" : "<"}{" "}
      </Text>,
    );

    for (let i = 0; i < questions.length; i++) {
      const isActive = currentTab === i;
      const hasAnswer = states[i].answer !== undefined;
      const label = questions[i].header;
      tabs.push(
        <Text key={`tab-${i}`}>
          {isActive ? (
            <Text bold color="cyan">
              {"["}
              {label}
              {"]"}
            </Text>
          ) : hasAnswer ? (
            <Text color="green">
              {"["}
              {symbols.success} {label}
              {"]"}
            </Text>
          ) : (
            <Text dimColor>
              {"["}
              {label}
              {"]"}
            </Text>
          )}
          {" "}
        </Text>,
      );
    }

    // Submit tab
    const submitActive = isSubmitTab;
    tabs.push(
      <Text key="submit-tab">
        {submitActive ? (
          <Text bold color={allAnswered ? "cyan" : undefined} dimColor={!allAnswered}>
            {"[Submit]"}
          </Text>
        ) : (
          <Text dimColor>{"[Submit]"}</Text>
        )}
      </Text>,
    );

    tabs.push(
      <Text key="right-arrow" dimColor>
        {" "}
        {symbols.arrow}
      </Text>,
    );

    return (
      <Box>
        {tabs}
      </Box>
    );
  };

  const renderQuestion = () => {
    if (!q || !qs) return null;
    const rows = [...q.options.map((o) => o.label), OTHER];

    return (
      <>
        <Text>
          {brand.tool(`  [${q.header}]`)}
          <Text dimColor>{`  (Q${currentTab + 1}/${questions.length})`}</Text>
        </Text>
        <Text> </Text>
        <Text bold>{`  ${q.question}`}</Text>
        {q.multiSelect && <Text dimColor>  (space to toggle, enter to confirm)</Text>}
        {qs.answer !== undefined && (
          <Text>
            {"  "}
            <Text color="green">
              {symbols.success} answered: {qs.answer}
            </Text>
            <Text dimColor> (press Enter to change)</Text>
          </Text>
        )}
        <Text> </Text>
        {rows.map((label, i) => {
          const isOther = i === rows.length - 1;
          const checked = q.multiSelect && !isOther && qs.selected.has(i);
          const mark = q.multiSelect && !isOther ? (checked ? "[x] " : "[ ] ") : "";
          const desc = !isOther ? q.options[i]?.description : undefined;
          return (
            <Text key={label}>
              {i === qs.cursor ? brand.tool(` ${symbols.prompt} `) : "   "}
              <Text color={i === qs.cursor ? "cyan" : undefined} dimColor={i !== qs.cursor}>
                {`${mark}${label}`}
                {desc ? ` — ${desc}` : ""}
              </Text>
            </Text>
          );
        })}
        {qs.otherMode && (
          <>
            <Text> </Text>
            <Text>
              {"  > "}
              <Text color="cyan">{qs.otherText}</Text>
              <Text dimColor>▌</Text>
            </Text>
          </>
        )}
      </>
    );
  };

  const renderSubmitPanel = () => {
    return (
      <>
        <Text bold>  {allAnswered ? "Review your answers:" : "Answer all questions first"}</Text>
        <Text> </Text>
        {questions.map((qn, i) => {
          const st = states[i];
          return (
            <Text key={qn.question}>
              {"  "}
              {st.answer !== undefined ? (
                <Text color="green">{symbols.success}</Text>
              ) : (
                <Text dimColor>{"○"}</Text>
              )}
              <Text>
                {" "}
                <Text bold>{qn.header}</Text>
                {": "}
                {st.answer !== undefined ? (
                  <Text>{st.answer}</Text>
                ) : (
                  <Text dimColor>(not answered)</Text>
                )}
              </Text>
            </Text>
          );
        })}
        <Text> </Text>
        {allAnswered ? (
          <Text color="cyan" bold>
            {"  Press Enter to submit, or ←/→ to review questions"}
          </Text>
        ) : (
          <Text dimColor>{"  Use ←/→ or Tab to navigate to unanswered questions"}</Text>
        )}
      </>
    );
  };

  return (
    <Box flexDirection="column" paddingLeft={1} paddingTop={1}>
      {isSubmitTab ? renderSubmitPanel() : renderQuestion()}
      <Text> </Text>
      {renderTabBar()}
      <Text dimColor>  ←/→ or Tab: switch questions  Esc: cancel</Text>
      <Text> </Text>
    </Box>
  );
}
