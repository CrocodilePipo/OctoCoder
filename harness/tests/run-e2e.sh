#!/usr/bin/env bash
# Automated E2E test runner for MewCode TS via tmux.
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
SESS="mewtest-ts"
PROMPTS_DIR="/home/qing/project/course/mewcode-course/tests/prompts"
RESULTS_FILE="/tmp/mewcode-ts-e2e-results.txt"
CWD="/home/qing/project/course/mewcode-ts-wt"

passed=0
failed=0
skipped=0

> "$RESULTS_FILE"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$RESULTS_FILE"; }

start_session() {
    tmux kill-session -t "$SESS" 2>/dev/null || true
    sleep 1
    cd "$CWD"
    tmux new-session -d -s "$SESS" -x 120 -y 40 "bun run src/main.tsx 2>/tmp/mewcode-ts-stderr.log"
    local elapsed=0
    while [ $elapsed -lt 15 ]; do
        if tmux capture-pane -t "$SESS" -p 2>/dev/null | grep -q "Type a message"; then
            log "Session started"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    log "FAIL: Session did not start"
    return 1
}

stop_session() {
    tmux kill-session -t "$SESS" 2>/dev/null || true
}

send_and_wait() {
    local msg="$1"
    local timeout="${2:-60}"

    tmux send-keys -t "$SESS" "$msg" Enter

    sleep 2
    local elapsed=2
    local prev=""
    local stable=0
    while [ $elapsed -lt $timeout ]; do
        local current
        current="$(tmux capture-pane -t "$SESS" -pS -500 2>/dev/null || echo '')"
        # Auto-approve permission dialogs
        if echo "$current" | grep -q "Permission required"; then
            tmux send-keys -t "$SESS" "a"
            sleep 1
            prev=""
            stable=0
            elapsed=$((elapsed + 1))
            continue
        fi
        # For slash commands and LLM, wait until "Type a message" reappears and output stabilizes
        if echo "$current" | grep -q "Type a message"; then
            if [ "$current" = "$prev" ]; then
                stable=$((stable + 1))
                if [ $stable -ge 2 ]; then
                    echo "$current"
                    return 0
                fi
            else
                stable=0
            fi
        fi
        prev="$current"
        sleep 2
        elapsed=$((elapsed + 2))
    done
    # Timeout — capture what we have
    tmux capture-pane -t "$SESS" -pS -500 2>/dev/null || echo ""
    return 1
}

check_assertion() {
    local output="$1"
    local assertion="$2"

    local type="${assertion%%:*}"
    local value="${assertion#*: }"

    case "$type" in
        CONTAINS)
            echo "$output" | grep -qF "$value"
            ;;
        CONTAINS_ANY)
            local IFS='|'
            for v in $value; do
                if echo "$output" | grep -qi "$v"; then
                    return 0
                fi
            done
            return 1
            ;;
        CONTAINS_CI)
            echo "$output" | grep -qi "$value"
            ;;
        NOT_CONTAINS)
            local IFS='|'
            for v in $value; do
                if echo "$output" | grep -qi "$v"; then
                    return 1
                fi
            done
            return 0
            ;;
        COMPLETION)
            return 0
            ;;
        FILE_EXISTS)
            [ -f "$value" ]
            ;;
        FILE_NOT_EXISTS)
            [ ! -f "$value" ]
            ;;
        FILE_CONTENT)
            local file="${value%% contains *}"
            local content="${value#* contains \"}"
            content="${content%\"}"
            grep -qF "$content" "$file" 2>/dev/null
            ;;
        *)
            return 0
            ;;
    esac
}

extract_prompt() {
    # Extract all ```text blocks, join with newlines
    sed -n '/^```text$/,/^```$/p' "$1" | grep -v '```'
}

extract_assertions() {
    sed -n '/^```assertions$/,/^```$/p' "$1" | grep -v '```' | grep -v '^$'
}

run_test() {
    local file="$1"
    local test_id
    test_id="$(basename "$file" .md)"

    local prompt
    prompt="$(extract_prompt "$file")"

    local assertions
    assertions="$(extract_assertions "$file")"

    local test_timeout
    test_timeout="$(sed -n 's/^timeout: *//p' "$file" | head -1)"
    test_timeout="${test_timeout:-90}"
    # Cap at 300s for CI sanity
    if [ "$test_timeout" -gt 300 ] 2>/dev/null; then
        test_timeout=300
    fi

    if [ -z "$prompt" ]; then
        log "SKIP $test_id: no prompt"
        skipped=$((skipped + 1))
        return
    fi

    log "RUN  $test_id ..."

    # Handle multi-line prompts (send each line)
    local output=""
    local line_count=0
    while IFS= read -r line; do
        line_count=$((line_count + 1))
    done <<< "$prompt"

    if [ $line_count -le 1 ]; then
        output="$(send_and_wait "$prompt" "$test_timeout")" || true
    else
        # Multi-line: send each line, only wait after the last
        local i=0
        while IFS= read -r line; do
            i=$((i + 1))
            if [ $i -lt $line_count ]; then
                tmux send-keys -t "$SESS" "$line" Enter
                # For slash commands wait briefly, for LLM prompts wait longer
                if [[ "$line" == /* ]]; then
                    sleep 5
                else
                    # Wait for LLM to finish before sending next prompt
                    local wait_elapsed=0
                    while [ $wait_elapsed -lt 120 ]; do
                        sleep 3
                        wait_elapsed=$((wait_elapsed + 3))
                        local wait_pane
                        wait_pane="$(tmux capture-pane -t "$SESS" -pS -100 2>/dev/null || echo '')"
                        if echo "$wait_pane" | grep -q "Permission required"; then
                            tmux send-keys -t "$SESS" "a"
                            sleep 1
                            continue
                        fi
                        if echo "$wait_pane" | grep -q "Type a message"; then
                            sleep 2
                            break
                        fi
                    done
                fi
            else
                if [[ "$line" == "/rewind" ]]; then
                    # /rewind opens a two-phase dialog — send Enter to select last snapshot, then Enter to select "Restore code and conversation"
                    tmux send-keys -t "$SESS" "$line" Enter
                    sleep 3
                    tmux send-keys -t "$SESS" "" Enter  # Select last snapshot (default cursor)
                    sleep 2
                    tmux send-keys -t "$SESS" "" Enter  # Select first option (Restore code and conversation)
                    sleep 3
                    output="$(tmux capture-pane -t "$SESS" -pS -500 2>/dev/null || echo '')"
                else
                    output="$(send_and_wait "$line" "$test_timeout")" || true
                fi
            fi
        done <<< "$prompt"
    fi

    if [ -z "$output" ]; then
        output="$(tmux capture-pane -t "$SESS" -pS -500 2>/dev/null || echo '')"
    fi

    # Check assertions
    local all_pass=true
    while IFS= read -r assertion; do
        [ -z "$assertion" ] && continue
        if ! check_assertion "$output" "$assertion"; then
            log "FAIL $test_id: assertion failed: $assertion"
            all_pass=false
            break
        fi
    done <<< "$assertions"

    if $all_pass; then
        log "PASS $test_id"
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
}

# ---- Main ----

# Filter: only run tests we can actually test (need a fresh session per batch)
TESTABLE_TESTS=(
    # P0: Core
    ch02_llm_streaming/T02-01_streaming.md
    ch03_tools/T03-01_read_file.md
    ch03_tools/T03-02_write_edit.md
    ch03_tools/T03-03_bash.md
    ch03_tools/T03-04_glob_grep.md
    ch04_agent_loop/T04-01_multi_tool_chain.md
    ch05_system_prompt/T05-01_identity.md
    ch06_permissions/T06-01_dangerous_cmd.md
    ch06_permissions/T06-03_plan_readonly.md
    # MCP
    ch07_mcp/T07-01_context7.md
    ch07_mcp/T07-02_playwright.md
    # Context management
    ch08_context_mgmt/T08-01_compact.md
    # Memory + session
    ch09_memory/T09-01_instructions.md
    ch09_memory/T09-02_session.md
    # Slash commands
    ch10_slash_commands/T10-01_help.md
    ch10_slash_commands/T10-02_status.md
    ch10_slash_commands/T10-04_unknown_cmd.md
    # Skills
    ch11_skills/T11-01_skill_list.md
    ch11_skills/T11-02_skill_invoke.md
    # Hooks
    ch12_hooks/T12-01_hook_pre_tool_use.md
    # Sub-agents
    ch13_subagent/T13-01_fork_mode.md
    ch13_subagent/T13-02_definition_mode.md
    # Worktree
    ch14_worktree/T14-01_create_list.md
    # Teams
    ch15_teams/T15-01_team_coordination.md
    # Rewind
    ch16_rewind/T16-01_rewind_basic.md
)

# Clean up test artifacts
rm -f /tmp/mewcode_test_write.txt /tmp/plan_readonly_test.txt /tmp/mewcode-rewind-test.txt

log "Starting MewCode TS E2E tests (${#TESTABLE_TESTS[@]} tests)..."

for t in "${TESTABLE_TESTS[@]}"; do
    start_session || { log "FAIL: could not start session for $t"; failed=$((failed+1)); continue; }
    run_test "$PROMPTS_DIR/$t"
    stop_session
    sleep 1
done

log ""
log "===== RESULTS ====="
log "Passed: $passed"
log "Failed: $failed"
log "Skipped: $skipped"
log "Total:  $((passed + failed + skipped))"
