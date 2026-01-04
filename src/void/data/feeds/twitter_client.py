"""
Twitter/X API v2 client for VOID.

Handles search, trends, and user lookups with rate limiting.
"""

import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from void.config import config

import structlog

logger = structlog.get_logger()


class TwitterClient:
    """Async Twitter API v2 client."""

    def __init__(self):
        self.bearer_token = config.twitter.bearer_token.get_secret_value()
        self.api_key = config.twitter.api_key.get_secret_value()
        self.api_secret = config.twitter.api_secret.get_secret_value()

        # API endpoints
        self.base_url = "https://api.twitter.com/2"
        self.search_url = f"{self.base_url}/tweets/search/recent"
        self.trends_url = f"{self.base_url}/trends/by/place"  # WOEID format

        # Rate limiting
        self.rate_limit_reset = 0
        self.remaining_requests = 450  # Twitter v2 default

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with bearer token."""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated API request with retry.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body for POST requests

        Returns:
            Response data as dict
        """
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(
                        url,
                        headers=self._get_headers(),
                        params=params,
                    )
                elif method.upper() == "POST":
                    response = await client.post(
                        url,
                        headers=self._get_headers(),
                        json=json_data,
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Update rate limit info from headers
                self.remaining_requests = int(
                    response.headers.get("x-rate-limit-remaining", 0)
                )
                self.rate_limit_reset = int(
                    response.headers.get("x-rate-limit-reset", 0)
                )

                response.raise_for_status()

                data = response.json()

                logger.debug(
                    "twitter_api_success",
                    endpoint=endpoint,
                    remaining=self.remaining_requests,
                )

                return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited
                    reset_time = datetime.fromtimestamp(self.rate_limit_reset)
                    logger.warning(
                        "twitter_rate_limited",
                        reset_time=reset_time.isoformat(),
                    )
                    raise

                logger.error(
                    "twitter_http_error",
                    status_code=e.response.status_code,
                    response=e.response.text,
                )
                raise

            except Exception as e:
                logger.error("twitter_api_error", error=str(e))
                raise

    async def search_tweets(
        self,
        query: str,
        max_results: int = 100,
        tweet_fields: Optional[List[str]] = None,
        user_fields: Optional[List[str]] = None,
        expansions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search recent tweets.

        Args:
            query: Search query (Twitter query syntax)
            max_results: Max tweets to return (10-100)
            tweet_fields: Tweet fields to return
            user_fields: User fields to return
            expansions: Expansions to include

        Returns:
            List of tweet data
        """
        if tweet_fields is None:
            tweet_fields = [
                "created_at", "author_id", "public_metrics",
                "context_annotations", "entities", "source",
            ]

        if user_fields is None:
            user_fields = ["username", "name", "public_metrics", "verified"]

        if expansions is None:
            expansions = ["author_id"]

        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": ",".join(tweet_fields),
            "user.fields": ",".join(user_fields),
            "expansions": ",".join(expansions),
        }

        logger.info(
            "twitter_search",
            query=query,
            max_results=max_results,
        )

        data = await self._request("GET", "/tweets/search/recent", params=params)

        # Extract tweets and user info
        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {u["id"]: u for u in includes.get("users", [])}

        # Enrich tweets with user info
        for tweet in tweets:
            author_id = tweet.get("author_id")
            if author_id and author_id in users:
                tweet["author_data"] = users[author_id]

        return tweets

    async def search_market_tweets(
        self,
        market_question: str,
        keywords: List[str],
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search tweets relevant to a prediction market.

        Args:
            market_question: Market question
            keywords: Relevant keywords
            max_results: Max tweets

        Returns:
            List of relevant tweets
        """
        # Build search query
        query_parts = []

        # Add market keywords (limit to 5 to avoid query too long)
        for kw in keywords[:5]:
            query_parts.append(f'"{kw}"')

        # Add market-specific terms
        query_parts.append("(polymarket OR prediction OR market OR betting)")

        query = " OR ".join(query_parts)

        # Search with language filter (English only)
        query += " lang:en"

        tweets = await self.search_tweets(
            query=query,
            max_results=max_results,
        )

        logger.info(
            "market_tweets_collected",
            market_question=market_question[:50],
            tweets_found=len(tweets),
        )

        return tweets

    async def get_trends(
        self,
        woeid: int = 1,  # 1 = Worldwide
    ) -> List[Dict[str, Any]]:
        """
        Get trending topics.

        Args:
            woeid: Where On Earth ID (1 = worldwide)

        Returns:
            List of trending topics
        """
        # Note: Twitter API v2 trends endpoint might not be available
        # This is a placeholder for v1.1 compatibility or future v2 support

        logger.warning(
            "twitter_trends_not_implemented",
            note="Twitter API v2 doesn't fully support trends yet",
        )

        # Return empty for now
        return []

    async def get_user_info(
        self,
        username: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get user information by username.

        Args:
            username: Twitter username (without @)

        Returns:
            User data
        """
        try:
            params = {
                "user.fields": "username,name,public_metrics,verified,description,created_at",
            }

            data = await self._request("GET", f"/users/by/username/{username}", params=params)
            return data.get("data")

        except Exception as e:
            logger.error("get_user_info_error", username=username, error=str(e))
            return None

    async def check_rate_limit(self) -> Dict[str, Any]:
        """
        Check current rate limit status.

        Returns:
            Dict with rate limit info
        """
        return {
            "remaining": self.remaining_requests,
            "reset": datetime.fromtimestamp(self.rate_limit_reset).isoformat(),
            "reset_in_seconds": self.rate_limit_reset - datetime.utcnow().timestamp(),
        }


__all__ = ["TwitterClient"]
