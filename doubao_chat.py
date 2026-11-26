#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doubao_chat.py — 豆包 Web 多轮对话协议复现（纯 Python，零外部运行时）

协议层：复现 POST /chat/completion 的请求构造 + SSE 解析 + 多轮状态维护。
签名层：a_bogus 用纯 Python（abogus_py，逆向实现）实时生成；
        msToken 由 mssdk 反向实现 + xmst 提供（见 refresh_xmst.py）。

运行：
    python doubao_chat.py

依赖：仅 Python 标准库 + 同目录 abogus_py.py / mssdk.py
"""

import argparse
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.parse

import abogus_py
import mssdk

BASE = "https://www.doubao.com"
PATH = "/chat/completion"
HERE = os.path.dirname(os.path.abspath(__file__))
IDENTITY_FILE = os.path.join(HERE, "doubao_identity.json")
FINGERPRINT_FILE = os.path.join(HERE, "fingerprint_template.json")

# 当前豆包 chat 的 bdms 参数（从活体页面确认）
AID = 497858
PAGE_ID = 1
BDMS_VERSION = "1.0.1.20-alpha.08"


# ---------------------------------------------------------------------------
# 身份 / 设备参数
# ---------------------------------------------------------------------------
class Identity:
    def __init__(self, path=IDENTITY_FILE):
        with open(path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    @property
    def cookies(self) -> dict:
        return self.data["cookies"]

    @property
    def device(self) -> dict:
        return self.data["device"]

    @property
    def bot_id(self) -> str:
        return self.data["user"]["bot_id"]

    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())


# ---------------------------------------------------------------------------
# 签名器：msToken 提供 + a_bogus 生成
# ---------------------------------------------------------------------------
class Signer:
    def ms_token(self) -> str:
        raise NotImplementedError("msToken 需要从浏览器/mssdk 获取，尚未实现")

    def a_bogus(self, query_without_abogus: str, body: str) -> str:
        raise NotImplementedError


class StaticSigner(Signer):
    """一次性签名：仅用于对照/单发验证，多轮会失效。"""
    def __init__(self, ms_token: str, a_bogus: str):
        self._ms = ms_token
        self._ab = a_bogus

    def ms_token(self) -> str:
        return self._ms

    def a_bogus(self, query_without_abogus: str, body: str) -> str:
        return self._ab


class PythonAbogusSigner(Signer):
    """a_bogus 用纯 Python（abogus_py，逆向实现）实时生成；msToken 由外部提供。"""
    def __init__(self, ms_token_provider, ua=None, page_id=PAGE_ID, aid=AID, version=BDMS_VERSION):
        self._ms = ms_token_provider
        self._ua = ua or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        self._page_id = page_id
        self._aid = aid
        self._version = version
        self._abogus = abogus_py.Abogus(self._ua)

    def ms_token(self) -> str:
        v = self._ms() if callable(self._ms) else self._ms
        return v or ""

    def a_bogus(self, query_without_abogus: str, body: str) -> str:
        return self._abogus.calculate(query_without_abogus, body, self._page_id, self._aid, self._version)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# 协议客户端
# ---------------------------------------------------------------------------
class DoubaoChat:
    def __init__(self, identity: Identity, signer: Signer):
        self.id = identity
        self.signer = signer
        self.conversation_id = ""
        self.section_id = ""
        self.last_message_index = None
        self._ms_token = None  # 动态 token；None 时用 signer 提供的默认值
        self._last_meta = {}
        self._last_a_bogus = None
        self._last_ms_token = None

    def _get_token(self) -> str:
        return self._ms_token or self.signer.ms_token()

    def _refresh_token(self) -> bool:
        """纯 Python 刷新 msToken（现场生成 strData → /web/r/token），成功则更新并回填 json。"""
        try:
            token = mssdk.refresh_ms_token(self.id.device["user_agent"], FINGERPRINT_FILE)
        except Exception as e:
            print(f"[刷新 msToken 失败] {e}")
            return False
        if not token:
            return False
        self._ms_token = token
        try:
            with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["xmst"] = token
            data.setdefault("captured", {})["msToken"] = token
            with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
        except Exception:
            pass
        print(f"[已自动刷新 msToken] {token[:30]}...")
        return True

    def _build_body(self, text: str) -> dict:
        now_ms = int(time.time() * 1000)
        local_message_id = str(uuid.uuid1())
        block_id = str(uuid.uuid4())
        unique_key = str(uuid.uuid1())
        first_turn = (self.conversation_id == "")

        client_meta = {
            "bot_id": self.id.bot_id,
            "local_permissions": [
                {"permission_name": "ACCESS_COARSE_LOCATION", "status": 3},
                {"permission_name": "ACCESS_FINE_LOCATION", "status": 3},
                {"permission_name": "ACCESS_BACKGROUND_LOCATION", "status": 3},
            ],
        }
        if first_turn:
            client_meta["local_conversation_id"] = f"local_{now_ms}"
            client_meta["conversation_id"] = ""
            client_meta["last_section_id"] = ""
            client_meta["last_message_index"] = None
        else:
            client_meta["conversation_id"] = self.conversation_id
            client_meta["last_section_id"] = self.section_id
            client_meta["last_message_index"] = self.last_message_index

        option = {
            "send_message_scene": "",
            "create_time_ms": now_ms,
            "collect_id": "",
            "is_audio": False,
            "answer_with_suggest": False,
            "agent_mode": 2,
            "tts_switch": False,
            "need_deep_think": 0,
            "click_clear_context": False,
            "from_suggest": False,
            "is_regen": False,
            "is_replace": False,
            "is_from_click_option": False,
            "is_from_click_softlink": False,
            "disable_sse_cache": False,
            "select_text_action": "",
            "is_select_text": False,
            "resend_for_regen": False,
            "scene_type": 0,
            "unique_key": unique_key,
            "start_seq": 0,
            "need_create_conversation": first_turn,
            "regen_query_id": [],
            "edit_query_id": [],
            "regen_instruction": "",
            "no_replace_for_regen": False,
            "message_from": 0,
            "shared_app_name": "",
            "shared_app_id": "",
            "sse_recv_event_options": {"support_chunk_delta": True},
            "support_lazy_fetch_stream": True,
            "is_ai_playground": False,
            "is_old_user": True,
            "queue_client_state": {"queue_enabled": True, "queue_is_empty": True, "queue_submit_mode": 2},
            "recovery_option": {"is_recovery": False, "req_create_time_sec": int(time.time()), "append_sse_event_scene": 0},
            "message_storage_type": 0,
            "related_deleted_message_ids": {},
            "connector_info_list": [],
            "model_config": {"model_item_key": "0", "model_extra_params": {}, "reasoning_effort": 3},
            "aggregate_params": {
                "mention_skill_list": "[]",
                "mention_plugin_list": "[]",
                "mention_ext": "[{}]",
                "conversation_mode": "1" if first_turn else "",
                "mode_id": "1",
                "model_item_key": "0",
                "agent_mode": "2",
                "reasoning_effort": "3",
                "provider_id": "",
            },
            "conversation_mode": 1,
        }

        if first_turn:
            option["conversation_init_option"] = {"need_ack_conversation": True}
            option["conversation_init_ext"] = {"model_item_key": "0", "reasoning_effort": "3", "mode_id": "1"}
            option["general_task_param"] = {"server_do_compare": True}
        else:
            option["general_task_param"] = {"runtime_type": 0, "agent_task_param": {}, "project_id": "", "server_do_compare": True}

        ext = {
            "agent_mode": "2",
            "use_deep_think": "0",
            "general_task_param": json.dumps(option["general_task_param"], ensure_ascii=False, separators=(",", ":")),
            "collection_id": "",
            "is_finish": "1",
            "commerce_credit_config_enable": "0",
        }
        if first_turn:
            ext["sub_conv_firstmet_type"] = "1"
            ext["conversation_init_option"] = "{\"need_ack_conversation\":true}"

        message = {
            "local_message_id": local_message_id,
            "content_block": [{
                "block_type": 10000,
                "content": {
                    "text_block": {"text": text, "icon_url": "", "icon_url_dark": "", "summary": ""},
                    "pc_event_block": "",
                },
                "block_id": block_id,
                "parent_id": "",
                "meta_info": [],
                "extra_info": {},
                "append_fields": [],
            }],
            "message_status": 0,
        }

        return {
            "client_meta": client_meta,
            "messages": [message],
            "option": option,
            "user_context": [],
            "ext": ext,
        }

    # ---- 构造「不含 a_bogus、含 msToken」的 query 与 URL ----
    def _build_query_without_abogus(self, ms_token: str) -> str:
        d = self.id.device
        q = [
            ("aid", d["aid"]),
            ("device_id", d["device_id"]),
            ("device_platform", d["device_platform"]),
            ("doubao_device_platform", d["doubao_device_platform"]),
            ("doubao_pc_version", d["doubao_pc_version"]),
            ("fp", d["fp"]),
            ("language", d["language"]),
            ("os", d["os"]),
            ("pc_version", d["pc_version"]),
            ("pkg_type", d["pkg_type"]),
            ("real_aid", d["real_aid"]),
            ("region", d["region"]),
            ("samantha_web", d["samantha_web"]),
            ("sys_region", d["sys_region"]),
            ("tea_uuid", d["tea_uuid"]),
            ("tz_name", d["tz_name"]),
            ("use-olympus-account", d["use_olympus_account"]),
            ("version_code", d["version_code"]),
            ("web_id", d["web_id"]),
            ("web_platform", d["web_platform"]),
            ("web_tab_id", d["web_tab_id"]),
            ("msToken", ms_token),
        ]
        return urllib.parse.urlencode(q, safe="%")

    # ---- SSE 解析 ----
    def _iter_sse_events(self, resp):
        event, data_lines = None, []
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
            if line == "":
                if data_lines:
                    yield event, "\n".join(data_lines)
                event, data_lines = None, []
            elif line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            yield event, "\n".join(data_lines)

    # ---- 发送一条消息（非流式，返回完整回复）----
    def send(self, text: str) -> dict:
        chunks = []
        for chunk in self.stream(text):
            chunks.append(chunk)
        return {
            "text": "".join(chunks) or self._last_meta.get("brief", ""),
            "brief": self._last_meta.get("brief", ""),
            "meta": dict(self._last_meta),
            "a_bogus": self._last_a_bogus,
            "msToken": self._last_ms_token,
        }

    # ---- 流式发送：逐块 yield 文本增量（打字机式）----
    def stream(self, text: str):
        """生成器：边收边 yield 每个文本增量。

        完成后 self.conversation_id / section_id / last_message_index 已更新。

        用法：
            for chunk in chat.stream("你好"):
                print(chunk, end="", flush=True)
        """
        last_err = None
        for attempt in range(2):
            yielded_any = False
            try:
                for chunk in self._stream_once(text):
                    yielded_any = True
                    yield chunk
                return
            except Exception as e:
                last_err = e
                if attempt == 0 and not yielded_any and self._refresh_token():
                    continue
                raise
        raise last_err

    def stream_smooth(self, text: str, char_delay: float = 0.03):
        """平滑打字机：把 stream 的每个块拆成单字符 yield，字符间 sleep char_delay 秒。

        注意：纯显示层平滑，不改变服务端推送节奏；数据内容与 stream 完全一致。
        """
        for chunk in self.stream(text):
            for ch in chunk:
                yield ch
                time.sleep(char_delay)

    def _stream_once(self, text: str):
        ms_token = self._get_token()
        body = self._build_body(text)
        body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":"))

        query_no_ab = self._build_query_without_abogus(ms_token)
        a_bogus = self.signer.a_bogus(query_no_ab, body_str)
        url = BASE + PATH + "?" + query_no_ab + "&a_bogus=" + urllib.parse.quote(a_bogus, safe="")

        referer = BASE + "/chat/" + (self.conversation_id or "local_placeholder")
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", self.id.device["user_agent"])
        req.add_header("Referer", referer)
        req.add_header("Accept-Encoding", "identity")
        req.add_header("Cookie", self.id.cookie_header())
        req.data = body_str.encode("utf-8")

        self._last_a_bogus = a_bogus
        self._last_ms_token = ms_token
        self._last_meta = {}

        got_any = False
        with urllib.request.urlopen(req, timeout=180) as resp:
            for event, data in self._iter_sse_events(resp):
                if event == "SSE_ACK":
                    got_any = True
                    d = json.loads(data)
                    ack = d.get("ack_client_meta", {})
                    if ack.get("conversation_id"):
                        self.conversation_id = ack["conversation_id"]
                    if ack.get("section_id"):
                        self.section_id = ack["section_id"]
                    self._last_meta["timeout_conf"] = d.get("timeout_conf")
                elif event == "FULL_MSG_NOTIFY":
                    d = json.loads(data)
                    m = d.get("message", {})
                    self._last_meta["user_message_id"] = m.get("message_id")
                    self._last_meta["user_index"] = m.get("index_in_conv")
                elif event == "STREAM_MSG_NOTIFY":
                    got_any = True
                    d = json.loads(data)
                    self._last_meta["ai_message_id"] = d.get("meta", {}).get("message_id")
                    self._last_meta["ai_index"] = d.get("meta", {}).get("index_in_conv")
                    cb = d.get("content", {}).get("content_block", [])
                    if cb:
                        t = cb[0].get("content", {}).get("text_block", {}).get("text", "")
                        if t:
                            yield t
                elif event == "STREAM_CHUNK":
                    # patch_object=1 是 content_block 增量（第 2 个字符通常只走这里，无 CHUNK_DELTA）
                    d = json.loads(data)
                    for op in d.get("patch_op", []):
                        if op.get("patch_object") == 1 and op.get("patch_type") == 1:
                            for cb in op.get("patch_value", {}).get("content_block", []):
                                t = cb.get("content", {}).get("text_block", {}).get("text", "")
                                if t:
                                    got_any = True
                                    yield t
                elif event == "CHUNK_DELTA":
                    got_any = True
                    t = json.loads(data).get("text", "")
                    if t:
                        yield t
                elif event == "SSE_REPLY_END":
                    d = json.loads(data)
                    if d.get("end_type") == 1:
                        self._last_meta["brief"] = d.get("msg_finish_attr", {}).get("brief", "")

        if not got_any:
            raise RuntimeError("未收到有效 SSE 回复（可能 msToken 失效）")

        ai_index = self._last_meta.get("ai_index")
        if ai_index is not None:
            self.last_message_index = ai_index


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="豆包 Web 多轮对话（纯 Python）")
    ap.add_argument("--smooth", action="store_true", help="平滑打字机：字符间延迟逐字输出")
    ap.add_argument("--char-delay", type=float, default=0.03, help="平滑模式下每个字符的延迟秒数（默认 0.03）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    identity = Identity()

    ms_token = identity.data.get("xmst") or identity.data.get("captured", {}).get("msToken", "")
    signer = PythonAbogusSigner(ms_token_provider=ms_token)

    chat = DoubaoChat(identity, signer)
    print("豆包多轮对话（纯 Python，输入 exit 退出）")
    print("a_bogus 由 abogus_py 实时生成；msToken 用 xmst（稳定）。")
    if args.smooth:
        print(f"已开启平滑打字机（字符延迟 {args.char_delay}s）。")
    while True:
        try:
            text = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in ("exit", "quit", "q"):
            break
        try:
            print("\n豆包 > ", end="", flush=True)
            if args.smooth:
                for ch in chat.stream_smooth(text, args.char_delay):
                    print(ch, end="", flush=True)
            else:
                for chunk in chat.stream(text):
                    print(chunk, end="", flush=True)
            print()
            print(f"  [conv={chat.conversation_id} ai_index={chat._last_meta.get('ai_index')}]")
        except Exception as e:
            print(f"\n[错误] {e}")

    try:
        signer.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
