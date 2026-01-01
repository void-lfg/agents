"""
Polymarket Gamma API client for market discovery.

Fetches market metadata, prices, and order book data.
"""

import json
from typing import Optional, List, Dict, Any
from decimal import Decimal
import asyncio

import aiohttp
import structlog

from void.config import config

logger = structlog.get_logger()


class GammaClient:
    """
    Client for Polymarket Gamma API.

    Provides read-only access to market data.
    """

    def __init__(self):
        self.base_url = config.polymarket.gamma_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_markets(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        order: str = "id",
        ascending: bool = False,
        min_liquidity: Optional[float] = None,
        min_volume: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets from Gamma API.

        Args:
            active: Only active markets
            closed: Include closed markets
            limit: Max number of markets to return
            offset: Pagination offset
            order: Sort field
            ascending: Sort order
            min_liquidity: Minimum liquidity filter
            min_volume: Minimum volume filter

        Returns:
            List of market dictionaries
        """
        session = await self._get_session()

        params = {
            "active": active,
            "closed": closed,
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": ascending,
            "enableOrderBook": "true",  # Include order book data
        }

        # Add filters
        if min_liquidity is not None:
            params["liquidity_num_min"] = min_liquidity
        if min_volume is not None:
            params["volume_num_min"] = min_volume

        try:
            async with session.get(
                f"{self.base_url}/markets",
                params=params,
            ) as response:
                response.raise_for_status()
                data = await response.json()

                markets = data.get("data", [])

                logger.debug(
                    "markets_fetched",
                    count=len(markets),
                    active=active,
                )

                return markets

        except aiohttp.ClientError as e:
            logger.error("markets_fetch_failed", error=str(e))
            raise

    async def get_market_by_id(
        self,
        market_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch market by ID.

        Args:
            market_id: Polymarket market ID

        Returns:
            Market data or None if not found
        """
        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/markets/{market_id}",
            ) as response:
                if response.status == 404:
                    return None

                response.raise_for_status()
                data = await response.json()

                return data.get("data")

        except aiohttp.ClientError as e:
            logger.error(
                "market_fetch_failed",
                market_id=market_id,
                error=str(e),
            )
            raise

    async def get_market_by_slug(
        self,
        slug: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch market by URL slug.

        Args:
            slug: Market URL slug

        Returns:
            Market data or None if not found
        """
        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/markets/slug/{slug}",
            ) as response:
                if response.status == 404:
                    return None

                response.raise_for_status()
                data = await response.json()

                return data

        except aiohttp.ClientError as e:
            logger.error(
                "market_slug_fetch_failed",
                slug=slug,
                error=str(e),
            )
            raise

    async def search_markets(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search markets by query.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of matching markets
        """
        session = await self._get_session()

        params = {
            "q": query,
            "limit": limit,
        }

        try:
            async with session.get(
                f"{self.base_url}/search",
                params=params,
            ) as response:
                response.raise_for_status()
                data = await response.json()

                markets = data.get("data", [])

                logger.debug(
                    "markets_searched",
                    query=query,
                    count=len(markets),
                )

                return markets

        except aiohttp.ClientError as e:
            logger.error(
                "market_search_failed",
                query=query,
                error=str(e),
            )
            raise

    async def get_events(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch events (group of related markets).

        Args:
            limit: Max number of events
            offset: Pagination offset

        Returns:
            List of events
        """
        session = await self._get_session()

        params = {
            "limit": limit,
            "offset": offset,
            "order": "id",
            "ascending": False,
            "closed": False,
        }

        try:
            async with session.get(
                f"{self.base_url}/events",
                params=params,
            ) as response:
                response.raise_for_status()
                data = await response.json()

                events = data.get("data", [])

                logger.debug(
                    "events_fetched",
                    count=len(events),
                )

                return events

        except aiohttp.ClientError as e:
            logger.error("events_fetch_failed", error=str(e))
            raise

    def parse_token_ids(self, market: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract token IDs from market data.

        Args:
            market: Market data from Gamma API

        Returns:
            Dict with 'yes_token' and 'no_token'
        """
        try:
            # Parse clobTokenIds (JSON string)
            clob_tokens_json = market.get("clobTokenIds", "[]")
            clob_tokens = json.loads(clob_tokens_json)

            # Parse outcomes (JSON string)
            outcomes_json = market.get("outcomes", "[]")
            outcomes = json.loads(outcomes_json)

            return {
                "yes_token": clob_tokens[0] if len(clob_tokens) > 0 else None,
                "no_token": clob_tokens[1] if len(clob_tokens) > 1 else None,
                "yes_outcome": outcomes[0] if len(outcomes) > 0 else "YES",
                "no_outcome": outcomes[1] if len(outcomes) > 1 else "NO",
            }

        except (json.JSONDecodeError, IndexError) as e:
            logger.error(
                "token_id_parse_failed",
                market_id=market.get("id"),
                error=str(e),
            )
            return {
                "yes_token": None,
                "no_token": None,
                "yes_outcome": "YES",
                "no_outcome": "NO",
            }

    def parse_prices(self, market: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract prices from market data.

        Args:
            market: Market data from Gamma API

        Returns:
            Dict with 'yes_price' and 'no_price'
        """
        try:
            # Parse outcome prices (JSON string)
            prices_json = market.get("outcomePrices", "[0.5, 0.5]")
            prices = json.loads(prices_json)

            return {
                "yes_price": float(prices[0]) if len(prices) > 0 else 0.5,
                "no_price": float(prices[1]) if len(prices) > 1 else 0.5,
            }

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            logger.error(
                "price_parse_failed",
                market_id=market.get("id"),
                error=str(e),
            )
            return {
                "yes_price": 0.5,
                "no_price": 0.5,
            }


__all__ = ["GammaClient"]
