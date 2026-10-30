"""Base specialist agent implementation handling bounded context, retries, and metrics."""

import time
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.llm.provider import LLMError, LLMProvider, LLMValidationError, ModelTier
from app.agents.prompts.registry import PromptRegistry
from app.core.config import settings
from app.core.logging import logger

T = TypeVar("T", bound=BaseModel)


class BaseSpecialistAgent:
    """Base class for all CodeGuard review specialist agents."""

    def __init__(
        self,
        agent_name: str,
        prompt_version: str,
        provider: LLMProvider,
        model_tier: ModelTier = ModelTier.REASONING,
        version: str = "1.0.0",
    ):
        self.agent_name = agent_name
        self.prompt_version = prompt_version
        self.provider = provider
        self.model_tier = model_tier
        self.version = version

    def _format_valid_lines(self, changed_lines_by_file: dict[str, dict[str, list[int]]]) -> str:
        """Format allowed review lines per file to constrain model line placement."""
        lines_summary = []
        for file_path, side_dict in changed_lines_by_file.items():
            right_lines = side_dict.get("RIGHT", [])
            left_lines = side_dict.get("LEFT", [])
            lines_summary.append(
                f"- File: `{file_path}`\n"
                f"  Valid Head (RIGHT) lines: {sorted(right_lines) if right_lines else 'None'}\n"
                f"  Valid Base (LEFT) lines: {sorted(left_lines) if left_lines else 'None'}"
            )
        return "\n".join(lines_summary) if lines_summary else "No changed lines supplied."

    def _truncate_context_budget(self, text: str, max_chars: int = 16000) -> str:
        """Truncate text deterministically without breaking in the middle if possible."""
        if len(text) <= max_chars:
            return text
        logger.info(
            f"Context exceeds budget ({len(text)} > {max_chars} chars). Applying deterministic truncation.",
            extra={"agent": self.agent_name},
        )
        return text[:max_chars] + "\n\n[... Context truncated to respect token budget ...]"

    async def execute_structured_with_retry(
        self,
        user_prompt: str,
        response_schema: type[T],
        max_retries: int | None = None,
    ) -> tuple[T, dict[str, Any]]:
        """
        Execute LLM generation with schema validation and automatic retry on malformed output.
        Returns the parsed data and the agent_run execution metadata dictionary.
        """
        prompt_template = PromptRegistry.get(self.prompt_version)
        retries = max_retries if max_retries is not None else settings.AGENT_MAX_RETRIES

        t_start = time.perf_counter()
        start_time = datetime.now(UTC)
        current_prompt = user_prompt
        attempt = 0
        last_error: Exception | None = None
        total_in_tokens = 0
        total_out_tokens = 0
        total_tokens = 0
        total_cost = 0.0
        model_used = "unknown"

        while attempt <= retries:
            try:
                response = await self.provider.generate_structured(
                    prompt=current_prompt,
                    response_schema=response_schema,
                    system_instruction=prompt_template.system_instruction,
                    model_tier=self.model_tier,
                )

                model_used = response.model_name
                total_in_tokens += response.token_usage.input_tokens
                total_out_tokens += response.token_usage.output_tokens
                total_tokens += response.token_usage.total_tokens
                total_cost += response.token_usage.estimated_cost

                latency_ms = (time.perf_counter() - t_start) * 1000.0
                end_time = datetime.now(UTC)

                run_metadata = {
                    "agent_name": self.agent_name,
                    "agent_version": self.version,
                    "prompt_version": self.prompt_version,
                    "model_name": model_used,
                    "status": "COMPLETED",
                    "started_at": start_time,
                    "completed_at": end_time,
                    "input_tokens": total_in_tokens,
                    "output_tokens": total_out_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost": round(total_cost, 6),
                    "latency_ms": round(latency_ms, 2),
                    "retry_count": attempt,
                    "error_message": None,
                }
                return response.data, run_metadata

            except LLMValidationError as val_err:
                attempt += 1
                last_error = val_err
                if attempt > retries:
                    break
                logger.warning(
                    f"{self.agent_name} output validation failed on attempt {attempt}: {val_err}. Retrying with schema feedback...",
                )
                current_prompt = (
                    f"{user_prompt}\n\n"
                    f"IMPORTANT ERROR FEEDBACK FROM PREVIOUS ATTEMPT:\n"
                    f"Your previous output failed validation with error: {val_err}\n"
                    f"Please correct your response to strictly match the requested JSON schema."
                )
            except LLMError as llm_err:
                attempt += 1
                last_error = llm_err
                if not llm_err.retryable or attempt > retries:
                    break
                logger.warning(
                    f"{self.agent_name} LLM transient error on attempt {attempt}: {llm_err}. Retrying...",
                )
            except Exception as exc:
                attempt += 1
                last_error = exc
                break

        latency_ms = (time.perf_counter() - t_start) * 1000.0
        end_time = datetime.now(UTC)
        error_msg = f"{last_error.__class__.__name__}: {str(last_error)}"

        run_metadata = {
            "agent_name": self.agent_name,
            "agent_version": self.version,
            "prompt_version": self.prompt_version,
            "model_name": model_used,
            "status": "FAILED",
            "started_at": start_time,
            "completed_at": end_time,
            "input_tokens": total_in_tokens,
            "output_tokens": total_out_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": round(total_cost, 6),
            "latency_ms": round(latency_ms, 2),
            "retry_count": attempt,
            "error_message": error_msg,
        }

        logger.error(
            f"{self.agent_name} failed after {attempt} attempts: {error_msg}",
            exc_info=True,
        )
        raise LLMError(f"{self.agent_name} execution failed: {error_msg}", original_error=last_error)
