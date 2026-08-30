"""OpenAI 兼容接口的命令行聊天脚本。"""

from __future__ import annotations

from openai import OpenAI, OpenAIError


# 请填写 OpenAI 兼容服务的配置。
URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
APIKEY = ""  # 请填入你的 API Key
MODELNAME = "glm-5.2"


def validate_config() -> None:
    """确保所有必需配置均已填写。"""
    missing = [
        name
        for name, value in {
            "URL": URL,
            "APIKEY": APIKEY,
            "MODELNAME": MODELNAME,
        }.items()
        if not value.strip()
    ]
    if missing:
        raise SystemExit(f"请先填写配置项: {', '.join(missing)}")


def main() -> None:
    validate_config()

    client = OpenAI(
        base_url=URL,
        api_key=APIKEY,
        timeout=120.0,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "你是一个有帮助的 AI 助手。"}
    ]

    print("聊天已启动。输入 /clear 清空上下文，输入 /exit 退出。")
    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return

        if not user_input:
            continue
        if user_input.lower() in {"/exit", "/quit"}:
            print("已退出。")
            return
        if user_input.lower() == "/clear":
            messages = messages[:1]
            print("上下文已清空。")
            continue

        messages.append({"role": "user", "content": user_input})
        try:
            response = client.chat.completions.create(
                model=MODELNAME,
                messages=messages,
            )
        except OpenAIError as exc:
            messages.pop()
            print(f"请求失败: {exc}")
            continue

        answer = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": answer})
        print(f"AI: {answer}")


if __name__ == "__main__":
    main()
