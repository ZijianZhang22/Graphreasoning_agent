from __future__ import annotations
import os, time
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0

    def add(self, other: "Usage"):
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.latency_s += other.latency_s

@dataclass
class LLMResult:
    text: str
    usage: Usage

class LLM:
    def __init__(self, model: str, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        kwargs = {"api_key": os.getenv("OPENAI_API_KEY", "EMPTY")}
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    @retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(5))
    def complete(self, system: str, user: str, max_tokens: int = 300) -> LLMResult:
        t0 = time.perf_counter()
        r = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        dt = time.perf_counter() - t0
        u = getattr(r, "usage", None)
        return LLMResult(
            r.choices[0].message.content or "",
            Usage(
                calls=1,
                input_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(u, "completion_tokens", 0) or 0),
                latency_s=dt,
            ),
        )
