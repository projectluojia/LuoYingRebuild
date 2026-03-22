#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
USER_ID="u_regression"
USER_NAME="RegressionUser"
TITLE="WebMVP 回归测试"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[FAIL] 缺少命令: $1"
    exit 1
  fi
}

need_cmd curl
need_cmd python3

echo "[INFO] BASE_URL=$BASE_URL"

HTTP_CODE="$(curl -sS -o "$TMP_DIR/index.out" -w "%{http_code}" "$BASE_URL/")" || true
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "[FAIL] Web 服务不可达或未启动 (GET / => $HTTP_CODE)"
  echo "请先启动: cd src && uvicorn luoying_bot.main_web:create_app --factory --host 0.0.0.0 --port 8000"
  exit 1
fi
echo "[OK] Web 首页可访问"

echo "[STEP] 创建会话"
CREATE_CODE="$(curl -sS -o "$TMP_DIR/create.json" -w "%{http_code}" \
  -X POST "$BASE_URL/api/sessions" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"user_name\":\"$USER_NAME\",\"title\":\"$TITLE\"}")"
if [[ "$CREATE_CODE" != "200" ]]; then
  echo "[FAIL] 创建会话失败: HTTP $CREATE_CODE"
  cat "$TMP_DIR/create.json"
  exit 1
fi
SESSION_ID="$(python3 - <<'PY' "$TMP_DIR/create.json"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
sid = data.get("session", {}).get("session_id", "")
if not sid:
    raise SystemExit(1)
print(sid)
PY
)"
echo "[OK] session_id=$SESSION_ID"

echo "[STEP] 查询会话列表"
LIST_CODE="$(curl -sS -o "$TMP_DIR/list.json" -w "%{http_code}" \
  "$BASE_URL/api/sessions?user_id=$USER_ID")"
if [[ "$LIST_CODE" != "200" ]]; then
  echo "[FAIL] 查询会话列表失败: HTTP $LIST_CODE"
  cat "$TMP_DIR/list.json"
  exit 1
fi
python3 - <<'PY' "$TMP_DIR/list.json" "$SESSION_ID"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
sid = sys.argv[2]
sessions = data.get("sessions", [])
if not any(str(s.get("session_id", "")) == sid for s in sessions):
    raise SystemExit("session_id 不在会话列表中")
print("[OK] 会话列表包含新建会话")
PY

echo "[STEP] 发送消息（持久化链路）"
CHAT_CODE="$(curl -sS -o "$TMP_DIR/chat.json" -w "%{http_code}" \
  -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"user_id\":\"$USER_ID\",\"user_name\":\"$USER_NAME\",\"text\":\"你好，做一次稳定性回归\"}")"
if [[ "$CHAT_CODE" != "200" ]]; then
  echo "[FAIL] 发送消息失败: HTTP $CHAT_CODE"
  cat "$TMP_DIR/chat.json"
  exit 1
fi
python3 - <<'PY' "$TMP_DIR/chat.json"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
reply = str(data.get("reply", "")).strip()
if not reply:
    raise SystemExit("reply 为空")
print("[OK] /api/chat 返回 reply")
PY

echo "[STEP] 拉取历史消息"
MSG_CODE="$(curl -sS -o "$TMP_DIR/messages.json" -w "%{http_code}" \
  "$BASE_URL/api/sessions/$SESSION_ID/messages?user_id=$USER_ID")"
if [[ "$MSG_CODE" != "200" ]]; then
  echo "[FAIL] 拉取历史失败: HTTP $MSG_CODE"
  cat "$TMP_DIR/messages.json"
  exit 1
fi
python3 - <<'PY' "$TMP_DIR/messages.json"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
messages = data.get("messages", [])
if len(messages) < 2:
    raise SystemExit("历史消息数量不足，预期至少 2 条（user + assistant）")
roles = [str(m.get("role", "")) for m in messages]
if "user" not in roles or "assistant" not in roles:
    raise SystemExit(f"历史消息角色异常: {roles}")
print("[OK] 历史消息包含 user + assistant")
PY

echo "[STEP] 错误分支：跨用户访问同一会话"
ERR_CODE="$(curl -sS -o "$TMP_DIR/error.json" -w "%{http_code}" \
  -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"user_id\":\"other_user\",\"user_name\":\"Other\",\"text\":\"cross-user check\"}")"
if [[ "$ERR_CODE" == "200" ]]; then
  echo "[FAIL] 错误分支未触发，跨用户访问不应成功"
  exit 1
fi
python3 - <<'PY' "$TMP_DIR/error.json"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
if "detail" not in data:
    raise SystemExit("错误响应不是标准 JSON detail 结构")
print("[OK] 错误分支返回 JSON detail（前端可解析）")
PY

echo "[PASS] Web MVP 稳定化回归通过"
