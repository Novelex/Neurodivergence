"""The one shared pattern behind every agent (working spec §11, docs/agents.md).

Every agent is: one fixed, narrow system prompt + one schema-constrained GPT-4o call +
model/prompt version logged on the row or turn it produces. None of the 11 agents (or
the reranker) select tools or decide what runs next — that stays in the caller, never
inside an agent.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from neurodiversity.config import settings

T = TypeVar("T", bound=BaseModel)


@lru_cache
def get_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@dataclass
class AgentResult:
    output: BaseModel
    model: str
    prompt_version: str


def run_agent(
    system_prompt: str,
    user_message: str,
    output_model: type[T],
    prompt_version: str,
    model: str = "gpt-4o",
    temperature: float = 0.0,
) -> AgentResult:
    """One schema-constrained call. Never called with tools; never decides what runs next."""
    client = get_client()
    completion = client.beta.chat.completions.parse(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format=output_model,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise ValueError(f"Model returned no parsed output (refusal or parse failure): {completion}")
    return AgentResult(output=parsed, model=model, prompt_version=prompt_version)
