"""Abstract LLM client interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    usage: Optional[dict[str, int]] = None
    raw: Any = None


class LLMClient(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def generate(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        """Generate a text completion.

        Args:
            prompt: The user prompt.
            system: Optional system prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with the generated text.
        """
        ...

    def generate_structured(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        """Generate a structured (JSON) completion.

        Same as generate() but may use provider-specific features
        (e.g., JSON mode) to encourage valid JSON output.

        Default implementation appends a JSON enforcement instruction
        to the system prompt and delegates to generate().  Subclasses
        may override to use provider-native JSON mode.
        """
        json_system = (system + "\n\n" if system else "") + "You must respond with valid JSON only. No commentary."
        return self.generate(prompt, json_system, max_tokens, temperature)
