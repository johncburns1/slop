"""LLM provider adapters.

Implementations for various LLM providers (OpenAI, Anthropic, etc.)
that implement the LLMPort interface.
"""

from slop.adapters.llm.stand_in import StandInLLMAdapter

__all__ = ["StandInLLMAdapter"]
