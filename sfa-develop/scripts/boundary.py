import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


FIXED_BLOCK_REPLY = "不属于本部门的问题，无法提供答案"


@dataclass(frozen=True)
class Decision:
    should_answer: bool
    category: str
    reply: Optional[str]
    reasons: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_answer": self.should_answer,
            "category": self.category,
            "reply": self.reply,
            "reasons": list(self.reasons),
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _contains_any(text: str, needles: List[str]) -> bool:
    return any(n in text for n in needles)


def _match_any(text: str, patterns: List[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


def _has_code_signals(raw: str) -> bool:
    t = raw or ""
    tl = _norm(t)
    if "```" in t:
        return True
    if _match_any(
        t,
        [
            re.compile(r"\btraceback\b", re.I),
            re.compile(r"exception\b", re.I),
            re.compile(r"\b(npe|nullpointer)\b", re.I),
            re.compile(r"\btypeerror\b", re.I),
            re.compile(r"\bsyntaxerror\b", re.I),
            re.compile(r"\bsegmentation fault\b", re.I),
            re.compile(r"\bpanic:\b", re.I),
            re.compile(r"\bat\s+[\w.$]+\([\w.]+:\d+\)", re.I),
            re.compile(r"\bfile\s+\".+?\",\s+line\s+\d+", re.I),
            re.compile(r"\b\d{3}\s+(?:bad request|unauthorized|forbidden|not found|internal server error)\b", re.I),
        ],
    ):
        return True
    if _match_any(
        t,
        [
            re.compile(r"\b[a-zA-Z0-9_./-]+\.(py|js|ts|tsx|java|go|rs|cs|kt|swift|cpp|c|h|sql|yml|yaml|toml|json|xml|gradle)\b"),
            re.compile(r"\b(src|app|pages|components|controllers|services|dao|repository|middleware|routes)\b", re.I),
            re.compile(r"\b(api|http|grpc|rpc|sql|mysql|postgres|redis|kafka|mq)\b", re.I),
        ],
    ):
        return True
    dev_keywords = [
        "代码",
        "开发",
        "写个",
        "写一个",
        "实现",
        "脚本",
        "python",
        "javascript",
        "typescript",
        "java",
        "golang",
        "go",
        "rust",
        "c++",
        "cpp",
        "c#",
        "kotlin",
        "swift",
        "bash",
        "shell",
        "正则",
        "regex",
        "csv",
        "json",
        "xml",
        "编译",
        "构建",
        "打包",
        "依赖",
        "版本冲突",
        "单元测试",
        "测试用例",
        "日志",
        "堆栈",
        "报错",
        "异常",
        "崩溃",
        "复现",
        "接口",
        "返回 500",
        "返回500",
        "http 500",
        "http500",
        "sql",
        "数据库",
        "前端",
        "后端",
        "node",
        "npm",
        "pnpm",
        "yarn",
        "pip",
        "maven",
        "gradle",
        "git",
        "ci",
        "docker",
        "k8s",
        "kubectl",
    ]
    return _contains_any(tl, [k.lower() for k in dev_keywords])


def _has_bug_signals(raw: str) -> bool:
    tl = _norm(raw)
    bug_keywords = [
        "bug",
        "报错",
        "异常",
        "崩溃",
        "闪退",
        "500",
        "502",
        "503",
        "504",
        "复现",
        "错误日志",
        "日志",
        "堆栈",
        "error",
        "exception",
        "traceback",
        "npe",
        "nullpointer",
    ]
    return _contains_any(tl, [k.lower() for k in bug_keywords]) or _has_code_signals(raw)


def _is_customer_forward(raw: str) -> bool:
    tl = _norm(raw)
    forward_signals = [
        "客户频道",
        "客户群",
        "客户反馈",
        "客户转发",
        "转发客户",
        "转发：客户",
        "转发:客户",
        "转发：",
        "转发:",
        "客户：",
        "客户:",
    ]
    if _contains_any(tl, [s.lower() for s in forward_signals]):
        return True
    return False


def _has_non_dev_signals(raw: str) -> bool:
    tl = _norm(raw)
    non_dev_keywords = [
        "照片",
        "图片",
        "相册",
        "丢失",
        "找回",
        "恢复",
        "怎么操作",
        "怎么用",
        "使用说明",
        "规则是什么",
        "为什么这样",
        "退款",
        "发票",
        "会员",
        "充值",
        "客服",
        "投诉",
        "账号",
        "密码",
        "登录不上",
        "无法登录",
        "验证码",
        "权限申请",
        "业务问题",
        "运营",
        "数据怎么显示不对",
        "显示不对",
        "看不到",
    ]
    return _contains_any(tl, [k.lower() for k in non_dev_keywords])


def decide(text: str) -> Decision:
    raw = text or ""
    reasons: List[str] = []

    is_forward = _is_customer_forward(raw)
    if is_forward:
        reasons.append("customer_forward_signal")

    has_bug = _has_bug_signals(raw)
    if has_bug:
        reasons.append("bug_or_error_signal")

    has_code = _has_code_signals(raw)
    if has_code:
        reasons.append("dev_code_signal")

    non_dev = _has_non_dev_signals(raw)
    if non_dev:
        reasons.append("non_dev_signal")

    if is_forward and has_bug:
        return Decision(True, "customer_forwarded_bug", None, tuple(reasons))

    if has_code:
        return Decision(True, "dev_question", None, tuple(reasons))

    return Decision(False, "non_dev_or_out_of_scope", FIXED_BLOCK_REPLY, tuple(reasons))


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        payload = {"error": "missing_input", "usage": 'python3 boundary.py "<text>"'}
        sys.stdout.write("BLOCK\n" + json.dumps(payload, ensure_ascii=False) + "\n")
        return 2

    text = " ".join(argv[1:]).strip()
    d = decide(text)
    sys.stdout.write(("ALLOW" if d.should_answer else "BLOCK") + "\n")
    sys.stdout.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
    return 0 if d.should_answer else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
