"""
LLM API 客户端封装
使用 OpenAI SDK 统一处理 DeepSeek 等兼容 API
支持流式输出 (Streaming)
"""

import os
import json
from typing import Optional, Dict, Any, List, Generator
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import tiktoken


class LLMClient:
    """
    LLM API 客户端
    封装 OpenAI SDK，支持 DeepSeek 等兼容 API
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        max_tokens: int = 8192,
        temperature: float = 0.7
    ):
        """
        初始化客户端
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model_name: 模型名称
            max_tokens: 最大生成 Token 数
            temperature: 温度参数
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # 初始化 OpenAI 客户端（兼容 DeepSeek）
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0,
            max_retries=3
        )
        
        # 初始化 tokenizer（使用 cl100k_base，适用于大多数模型）
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = tiktoken.get_encoding("p50k_base")
    
    def count_tokens(self, text: str) -> int:
        """
        计算文本的 Token 数量
        
        Args:
            text: 输入文本
            
        Returns:
            int: Token 数量
        """
        return len(self.tokenizer.encode(text))
    
    def count_messages_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        计算消息列表的 Token 数量
        
        Args:
            messages: 消息列表
            
        Returns:
            int: Token 数量
        """
        total_tokens = 0
        for msg in messages:
            # 每条消息的固定开销
            total_tokens += 4
            # role 的 token
            total_tokens += self.count_tokens(msg.get("role", ""))
            # content 的 token
            total_tokens += self.count_tokens(msg.get("content", ""))
        # 回复的固定开销
        total_tokens += 2
        return total_tokens
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception)
    )
    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = None,
        temperature: float = None,
        json_mode: bool = False,
        stream: bool = False
    ) -> Optional[str]:
        """
        生成文本

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_tokens: 最大生成 Token 数
            temperature: 温度参数
            json_mode: 是否强制 JSON 输出
            stream: 是否使用流式输出

        Returns:
            Optional[str]: 生成的文本，失败返回 None
        """
        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 计算 Token 使用
        prompt_tokens = self.count_messages_tokens(messages)
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        effective_temperature = temperature if temperature is not None else self.temperature

        # 检查是否超出限制
        if prompt_tokens + effective_max_tokens > 32768:
            print(f"警告：Prompt Token 数 ({prompt_tokens}) + max_tokens ({effective_max_tokens}) 可能超出模型限制")

        # 调用 API
        if stream:
            return self._generate_stream(messages, effective_max_tokens, effective_temperature, json_mode)

        # 非流式模式
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=effective_max_tokens,
            temperature=effective_temperature,
            response_format={"type": "json_object"} if json_mode else None
        )

        # 提取响应
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            if content:
                return content.strip()

        print("API 响应为空")
        return None
    
    def _generate_stream(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        json_mode: bool
    ) -> str:
        """
        流式生成文本
        
        Args:
            messages: 消息列表
            max_tokens: 最大 Token 数
            temperature: 温度参数
            json_mode: 是否 JSON 模式
            
        Returns:
            str: 完整响应
        """
        collected_chunks = []
        
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            response_format={"type": "json_object"} if json_mode else None
        )
        
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    collected_chunks.append(delta.content)
                    # 实时输出到控制台
                    print(delta.content, end='', flush=True)
        
        print()  # 换行
        return ''.join(collected_chunks)
    
    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = None,
        temperature: float = None
    ) -> Generator[str, None, None]:
        """
        生成文本（生成器版本，用于实时输出到前端）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_tokens: 最大生成 Token 数
            temperature: 温度参数

        Yields:
            str: 生成的文本片段
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        effective_temperature = temperature if temperature is not None else self.temperature

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                stream=True
            )

            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            print(f"流式生成失败：{e}")
            return
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        生成 JSON 格式的响应

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_tokens: 最大生成 Token 数

        Returns:
            Optional[Dict]: 解析后的 JSON 数据，失败返回 None
        """
        content = None
        try:
            content = self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                json_mode=True
            )

            if content:
                return json.loads(content)
            return None

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败：{e}")
            print(f"原始响应：{content[:200] if content else 'None'}")
            return None


# 使用示例
if __name__ == "__main__":
    from .config import get_active_llm_config

    _active = get_active_llm_config()
    # 仅展示提供商名称与端点，不输出任何凭据字段
    _label = _active["label"]
    _provider_id = _active["provider"]
    print(f"测试提供商: {_label} ({_provider_id})")

    # 创建客户端
    client = LLMClient(
        api_key=_active["api_key"],
        base_url=_active["base_url"],
        model_name=_active["model"]
    )
    
    # 测试生成
    result = client.generate("你好，请做一个自我介绍")
    if result:
        print(f"生成结果：{result[:100]}...")
    
    # 测试 Token 计数
    text = "这是一段测试文本"
    tokens = client.count_tokens(text)
    print(f"Token 数：{tokens}")
