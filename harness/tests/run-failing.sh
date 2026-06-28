#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.bun/bin:$PATH"
SESS="mewtest-ts"
CWD="/home/qing/project/course/mewcode-ts-wt"

start_session() {
    tmux kill-session -t "$SESS" 2>/dev/null || true
    sleep 1
    cd "$CWD"
    tmux new-session -d -s "$SESS" -x 120 -y 40 "bun run src/main.tsx 2>/tmp/mewcode-ts-stderr.log"
    local elapsed=0
    while [ $elapsed -lt 15 ]; do
        if tmux capture-pane -t "$SESS" -p 2>/dev/null | grep -q "Type a message"; then
            echo "[OK] Session started"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    echo "[FAIL] Session did not start"
    return 1
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
    tmux capture-pane -t "$SESS" -pS -500 2>/dev/null || echo ""
}

stop_session() {
    tmux kill-session -t "$SESS" 2>/dev/null || true
}

echo "=== T05-01 Identity ==="
start_session
output="$(send_and_wait "你是谁？你叫什么名字？你能做哪些事情？" 30)"
echo "$output" | grep -iq "mewcode" && echo "[assertion] CONTAINS_CI mewcode: PASS" || echo "[assertion] CONTAINS_CI mewcode: FAIL"
if echo "$output" | grep -qi "Claude\|ChatGPT\|GPT-4"; then
    echo "[assertion] NOT_CONTAINS Claude|ChatGPT|GPT-4: FAIL"
    echo "[relevant output]:"
    echo "$output" | grep -i "claude\|chatgpt\|gpt" | head -5
else
    echo "[assertion] NOT_CONTAINS Claude|ChatGPT|GPT-4: PASS"
fi
stop_session

echo ""
echo "=== T16-01 Rewind ==="
rm -f /tmp/mewcode-rewind-test.txt
start_session

echo "[step 1] Write version 1..."
send_and_wait '在 /tmp/mewcode-rewind-test.txt 写入内容 "version 1: hello world"' 60 > /dev/null
echo "File after step 1: $(cat /tmp/mewcode-rewind-test.txt 2>/dev/null || echo 'NOT FOUND')"

echo "[step 2] Edit to version 2..."
send_and_wait '把 /tmp/mewcode-rewind-test.txt 的内容改成 "version 2: modified content"' 60 > /dev/null
echo "File after step 2: $(cat /tmp/mewcode-rewind-test.txt 2>/dev/null || echo 'NOT FOUND')"

echo "[step 3] /rewind..."
send_and_wait '/rewind' 15 > /dev/null
sleep 2
echo "File after rewind: $(cat /tmp/mewcode-rewind-test.txt 2>/dev/null || echo 'NOT FOUND')"

if grep -q "version 1" /tmp/mewcode-rewind-test.txt 2>/dev/null; then
    echo "[assertion] FILE_CONTENT version 1: PASS"
else
    echo "[assertion] FILE_CONTENT version 1: FAIL"
fi
stop_session
