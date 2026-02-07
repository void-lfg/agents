"""
AI-powered outcome verification for Oracle Latency strategy using Groq LLM.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum
import structlog

from void.config import config
from void.ai.groq_client import GroqClient

logger = structlog.get_logger()


class VerificationSource(str, Enum):
    """Verification source types."""
    GROQ = "groq"
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
    Verify real-world outcomes using Groq LLM (llama-3.3-70b-versatile).

    Confirms that:
    1. The event has actually concluded
    2. The predicted outcome is correct
    3. The evidence is strong enough to trade
    """

    def __init__(self):
        self.groq_client = GroqClient(
            api_key=config.ai.groq_api_key.get_secret_value(),
            model=config.ai.groq_model,
        )

    async def verify_outcome(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> VerificationResult:
        """
        Verify outcome using Groq LLM.

        Args:
            question: Market question
            predicted_outcome: Predicted outcome (YES/NO)
            market_category: Market category (sports, politics, etc.)
            sources: Data sources to use

        Returns:
            Verification result with confidence score
        """
        try:
            result = await self._verify_with_groq(
                question,
                predicted_outcome,
                market_category,
            )

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
                verified_at=datetime.now(timezone.utc).isoformat(),
            )

    async def _verify_with_groq(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify outcome using Groq LLM.

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
            # Call Groq API
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert at verifying real-world outcomes for prediction markets. "
                        "Provide accurate, factual answers based on your knowledge. "
                        "Be conservative with confidence scores - only give high confidence if you are certain."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            content = await self.groq_client.chat_completion(
                messages=messages,
                temperature=0.1,  # Low temperature for factual responses
                max_tokens=300,
            )

            # Extract confidence and reasoning
            confidence, reasoning = self._parse_response(content)

            logger.info(
                "groq_verification_complete",
                question=question[:50],
                predicted_outcome=predicted_outcome,
                confidence=confidence,
            )

            return VerificationResult(
                predicted_outcome=predicted_outcome,
                confidence=confidence,
                source=VerificationSource.GROQ,
                reasoning=reasoning,
                raw_data={"response": content},
                verified_at=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as e:
            logger.error("groq_verification_error", error=str(e))
            raise

    def _build_verification_prompt(
        self,
        question: str,
        predicted_outcome: str,
        market_category: Optional[str] = None,
    ) -> str:
        """Build verification prompt for Groq LLM."""
        category_hint = f"\nCategory: {market_category}" if market_category else ""

        prompt = f"""I need you to verify the outcome of a prediction market question.

**Market Question:** {question}{category_hint}

**Predicted Outcome:** {predicted_outcome}

**Task:**
1. Based on your knowledge, determine if this event has already concluded
2. If concluded, verify if the predicted outcome ({predicted_outcome}) is correct
3. Assess your confidence level (0.0 to 1.0)

**Requirements:**
- Base your answer ONLY on confirmed facts and official results you know about
- If the event hasn't concluded yet, confidence should be 0.0
- If you're uncertain about the outcome, lower your confidence accordingly
- Be conservative - only give confidence > 0.9 if you are absolutely certain

**Response Format (follow this exactly):**
CONCLUDED: [YES/NO]
OUTCOME_CORRECT: [YES/NO/UNKNOWN]
CONFIDENCE: [0.0-1.0]
REASONING: [Your brief reasoning]

Please respond:"""

        return prompt

    def _parse_response(self, content: str) -> tuple[float, str]:
        """
        Parse Groq response to extract confidence and reasoning.

        Args:
            content: Response content from Groq

        Returns:
            Tuple of (confidence, reasoning)
        """
        try:
            lines = content.strip().split("\n")
            confidence = 0.5
            reasoning = content
            concluded = False
            outcome_correct = False

            for line in lines:
                line = line.strip()
                if line.startswith("CONCLUDED:"):
                    concluded = "YES" in line.upper()
                elif line.startswith("OUTCOME_CORRECT:"):
                    outcome_correct = "YES" in line.upper()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        conf_str = line.split(":")[1].strip()
                        # Handle cases like "0.95" or "95%"
                        conf_str = conf_str.replace("%", "").strip()
                        confidence = float(conf_str)
                        if confidence > 1.0:
                            confidence = confidence / 100.0
                    except (ValueError, IndexError):
                        confidence = 0.5
                elif line.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip() if ":" in line else line

            # If event hasn't concluded or outcome is wrong, set low confidence
            if not concluded:
                confidence = 0.0
                reasoning = "Event has not concluded yet. " + reasoning
            elif not outcome_correct:
                confidence = min(confidence, 0.3)
                reasoning = "Predicted outcome may be incorrect. " + reasoning

            return confidence, reasoning

        except Exception as e:
            logger.error("response_parse_error", error=str(e))
            return 0.5, content


__all__ = [
    "OutcomeVerifier",
    "VerificationResult",
    "VerificationSource",
]
