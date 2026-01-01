"""
AI-powered outcome verification for Oracle Latency strategy using Z.ai GLM-4.7.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
import httpx
import structlog

from void.config import config

logger = structlog.get_logger()


class VerificationSource(str, Enum):
    """Verification source types."""
    ZAI = "zai"
    ESPN = "espn"
    BINANCE = "binance"
    MANUAL = "manual"


@dataclass
class VerificationResult:
    """Result of outcome verification."""

    predicted_outcome: str  # YES or NO
    confidence: float  # 0.0 to 1.0
    source: VerificationSource
    reasoning: str
    raw_data: dict
    verified_at: str  # ISO timestamp


class OutcomeVerifier:
    """
    Verify real-world outcomes using Z.ai GLM-4.7.

    Confirms that:
    1. The event has actually concluded
    2. The predicted outcome is correct
    3. The evidence is strong enough to trade
    """

    def __init__(self):
        self.api_key = config.ai.zai_api_key.get_secret_value()
        self.model = config.ai.zai_model
        self.api_url = "https://api.z.ai/api/paas/v4/chat/completions"

    async def verify_outcome(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> VerificationResult:
        """
        Verify outcome using Z.ai GLM-4.7.

        Args:
            question: Market question
            predicted_outcome: Predicted outcome (YES/NO)
            market_category: Market category (sports, politics, etc.)
            sources: Data sources to use

        Returns:
            Verification result with confidence score
        """
        # Default to Z.ai
        if not sources:
            sources = ["zai"]

        try:
            for source in sources:
                if source == "zai":
                    result = await self._verify_with_zai(
                        question,
                        predicted_outcome,
                        market_category,
                    )

                # If confidence is high enough, return
                if result.confidence >= config.ai.confidence_threshold:
                    return result

            # Return best result
            return result

        except Exception as e:
            logger.error(
                "verification_failed",
                question=question[:50],
                error=str(e),
            )
            # Return low confidence on error
            return VerificationResult(
                predicted_outcome=predicted_outcome,
                confidence=0.5,
                source=VerificationSource.MANUAL,
                reasoning=f"Verification failed: {str(e)}",
                raw_data={},
                verified_at="",
            )

    async def _verify_with_zai(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify outcome using Z.ai GLM-4.7.

        Args:
            question: Market question
            predicted_outcome: Predicted outcome
            market_category: Market category

        Returns:
            Verification result
        """
        # Build prompt
        prompt = self._build_verification_prompt(
            question,
            predicted_outcome,
            market_category,
        )

        try:
            # Call Z.ai API
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert at verifying real-world outcomes for prediction markets. Provide accurate, factual answers based on current events.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": 0.0,  # Deterministic
                        "top_p": 0.95,
                        "max_tokens": 200,
                        "do_sample": False,  # Synchronous call
                    },
                )

                response.raise_for_status()
                data = response.json()

                # Parse response
                content = data["choices"][0]["message"]["content"]

                # Extract confidence and reasoning
                confidence, reasoning = self._parse_zai_response(content)

                logger.info(
                    "zai_verification_complete",
                    question=question[:50],
                    predicted_outcome=predicted_outcome,
                    confidence=confidence,
                )

                return VerificationResult(
                    predicted_outcome=predicted_outcome,
                    confidence=confidence,
                    source=VerificationSource.ZAI,
                    reasoning=reasoning,
                    raw_data={"response": content},
                    verified_at="",
                )

        except httpx.HTTPStatusError as e:
            logger.error(
                "zai_http_error",
                status_code=e.response.status_code,
                response=e.response.text,
            )
            raise

        except Exception as e:
            logger.error("zai_verification_error", error=str(e))
            raise

    def _build_verification_prompt(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
    ) -> str:
        """Build verification prompt for Z.ai GLM-4.7."""
        prompt = f"""I need you to verify the outcome of a prediction market question.

**Market Question:** {question}

**Predicted Outcome:** {predicted_outcome}

**Task:**
1. Determine if this event has already concluded
2. Verify if the predicted outcome is correct
3. Assess your confidence level (0.0 to 1.0)

**Requirements:**
- Base your answer ONLY on confirmed facts and official results
- If the event hasn't concluded yet, say "NOT CONCLUDED"
- Provide your confidence as a decimal between 0.0 and 1.0
- Be conservative - if you're not 100% sure, lower your confidence

**Response Format:**
CONFIDENCE: [0.0-1.0]
REASONING: [Your reasoning here]

Please respond:"""

        return prompt

    def _parse_zai_response(self, content: str) -> tuple[float, str]:
        """
        Parse Z.ai response to extract confidence and reasoning.

        Args:
            content: Response content from Z.ai

        Returns:
            Tuple of (confidence, reasoning)
        """
        try:
            # Look for CONFIDENCE: line
            for line in content.split("\n"):
                if line.startswith("CONFIDENCE:"):
                    confidence_str = line.split(":")[1].strip()
                    confidence = float(confidence_str)
                    break
            else:
                # Default confidence if not found
                confidence = 0.75

            # Extract reasoning
            if "REASONING:" in content:
                reasoning = content.split("REASONING:")[1].strip()
            else:
                reasoning = content

            return confidence, reasoning

        except Exception as e:
            logger.error("zai_response_parse_error", error=str(e))
            return 0.5, content


__all__ = [
    "OutcomeVerifier",
    "VerificationResult",
    "VerificationSource",
]
