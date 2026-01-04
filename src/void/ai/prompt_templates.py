"""
Z.ai GLM prompt templates for VOID AI features.

All prompts optimized for GLM-4.7 model with context window management.
"""

from datetime import datetime


class PromptTemplates:
    """Centralized prompt templates for all AI interactions."""

    # ============== INTENT CLASSIFICATION ==============

    INTENT_CLASSIFICATION = """You are VOID's intent classifier. Analyze the user message and determine their intent.

Available intents:
1. PORTFOLIO_QUERY - Questions about account balance, P&L, performance
2. MARKET_RESEARCH - Questions about specific markets, prices, conditions
3. TRADING_ADVICE - Asking for recommendations, should I buy/sell
4. SIGNAL_ANALYSIS - Questions about trading signals, why was signal generated
5. GENERAL_KNOWLEDGE - General questions, how things work, help

User message: "{message}"

Respond with ONLY the intent name (e.g., "PORTFOLIO_QUERY"). No explanation.
"""

    # ============== CHAT SYSTEM PROMPT ==============

    SYSTEM_PROMPT = """You are VOID, an intelligent AI trading assistant for prediction markets.

Your capabilities:
• Analyze market conditions and trading opportunities
• Provide portfolio insights and performance analysis
• Explain trading signals and strategies
• Monitor social sentiment (Twitter, news)
• Research markets using knowledge base
• Give balanced trading advice (always mention risks)

Your personality:
• Professional but friendly
• Data-driven and analytical
• Cautious with risk (never encourage gambling)
• Transparent about uncertainties
• Helpful and educational

Important rules:
1. Never guarantee profits or promise returns
2. Always mention risks when suggesting trades
3. If uncertain, say "I don't have enough data"
4. Keep responses concise (under 500 words)
5. Use markdown for formatting
6. Be honest about model limitations

Current date: {current_date}
"""

    # ============== CONTEXT-AWARE CHAT ==============

    CHAT_WITH_CONTEXT = """{system_prompt}

USER CONTEXT:
{user_context}

CONVERSATION HISTORY:
{conversation_history}

Current market conditions:
{market_context}

Recent knowledge (last 24h):
{knowledge_summary}

User message: "{message}"

Provide a helpful, context-aware response:
"""

    # ============== MARKET RESEARCH ==============

    MARKET_RESEARCH = """Research this prediction market and provide a comprehensive analysis.

Market: {market_question}
Condition ID: {condition_id}
Current prices: YES ${yes_price} | NO ${no_price}
Liquidity: ${liquidity}
Volume 24h: ${volume_24h}
End date: {end_date}

ANALYSIS REQUIREMENTS:
1. Market Overview
   - What is this market predicting?
   - How does resolution work?
   - What are the key factors?

2. Sentiment Analysis (if available)
   - Twitter sentiment: {twitter_sentiment}
   - News coverage: {news_count} articles
   - Overall trend: {sentiment_trend}

3. Trading Considerations
   - Liquidity assessment
   - Spread analysis
   - Risk factors

4. Knowledge Base Insights
   {knowledge_insights}

5. Conclusion
   - Bullish/Bearish/Neutral
   - Confidence level (Low/Medium/High)
   - Key recommendation

Provide clear, actionable insights with data-backed reasoning.
"""

    # ============== SENTIMENT ANALYSIS ==============

    SENTIMENT_ANALYSIS = """Analyze the sentiment of this text and provide detailed scoring.

Text: "{text}"
Context: {context} (e.g., "market ID: 0x123", "general crypto")

Provide JSON response:
{{
    "score": <float from -1.0 (very negative) to +1.0 (very positive)>,
    "confidence": <float from 0.0 to 1.0>,
    "sentiment": "<negative|neutral|positive>",
    "key_points": ["<key insight 1>", "<key insight 2>", ...],
    "entities": ["<mentioned entities>"],
    "reasoning": "<brief explanation>"
}}

Only respond with valid JSON. No additional text.
"""

    # ============== TWEET SENTIMENT ==============

    TWEET_SENTIMENT = """Analyze sentiment of this tweet for prediction market trading.

Tweet: "{tweet}"
Author: @{author} ({followers} followers)
Metrics: {likes} likes, {retweets} retweets, {replies} replies
Posted: {timestamp}

Focus on:
• Market-relevant sentiment (ignore noise)
• Confidence level of author
• Potential market impact

Respond with JSON:
{{
    "score": <float -1.0 to +1.0>,
    "confidence": <float 0.0 to 1.0>,
    "market_relevance": <float 0.0 to 1.0>,
    "key_insight": "<one sentence summary>"
}}

Only JSON response.
"""

    # ============== KNOWLEDGE SUMMARIZATION ==============

    SUMMARIZE_TWEETS = """Summarize these tweets into key market insights.

Market: {market_id}
Tweets collected: {count}
Time range: last 24 hours

Tweets:
{tweets}

Create a concise summary (max 200 words) covering:
1. Overall sentiment trend
2. Key themes/discussion points
3. Influencer opinions (if any)
4. Notable events or news

Summary:
"""

    SUMMARIZE_NEWS = """Summarize news coverage for this market.

Market: {market_id}
Articles: {count}

News items:
{news_items}

Provide a structured summary (max 250 words):
1. Main narrative
2. Bullish factors
3. Bearish factors
4. Key developments
5. Uncertainties/risks

Summary:
"""

    # ============== TRADING ADVICE ==============

    TRADING_ADVICE = """Provide trading advice for this scenario.

USER PORTFOLIO:
{portfolio_summary}

MARKET UNDER CONSIDERATION:
{market_details}

USER QUESTION: "{question}"

Provide balanced advice covering:
1. Analysis of the opportunity
2. Risk assessment (1-10 scale)
3. Position sizing recommendation
4. Entry/exit considerations
5. Alternative options

Important:
• Never guarantee profits
• Always emphasize risks
• Consider user's portfolio size
• Suggest starting small if uncertain
• Mention diversification

Response:
"""

    # ============== SIGNAL EXPLANATION ==============

    EXPLAIN_SIGNAL = """Explain this trading signal in simple terms.

SIGNAL DETAILS:
Type: {signal_type}
Strategy: {strategy}
Market: {market_question}
Entry Price: ${entry_price}
Expected Payout: ${expected_payout}
Profit Margin: {profit_margin}%
Confidence: {confidence}%

VERIFICATION:
{verification_data}

MARKET CONTEXT:
{market_context}

Explain in plain language:
1. Why was this signal generated?
2. What's the trading opportunity?
3. What are the risks?
4. What action should user take?
5. What to monitor after execution?

Keep it simple and actionable.
"""

    # ============== PORTFOLIO ANALYSIS ==============

    PORTFOLIO_ANALYSIS = """Analyze this trading portfolio and provide insights.

PORTFOLIO SUMMARY:
{portfolio_summary}

POSITIONS:
{positions}

RECENT PERFORMANCE:
{performance_stats}

Provide analysis covering:
1. Overall portfolio health (Excellent/Good/Fair/Poor)
2. Strengths
3. Weaknesses/Risks
4. Diversification assessment
5. Recent performance drivers
6. Actionable recommendations (3-5 specific items)

Be constructive and specific. Use data points.
"""

    # ============== HELPERS ==============

    @staticmethod
    def format_system_prompt():
        """Format system prompt with current date."""
        return PromptTemplates.SYSTEM_PROMPT.format(
            current_date=datetime.utcnow().strftime("%Y-%m-%d")
        )

    @staticmethod
    def format_chat_context(system_prompt, user_context, history, market_context, knowledge, message):
        """Format chat prompt with all context."""
        return PromptTemplates.CHAT_WITH_CONTEXT.format(
            system_prompt=system_prompt,
            user_context=user_context,
            conversation_history=history,
            market_context=market_context,
            knowledge_summary=knowledge,
            message=message
        )

    @staticmethod
    def truncate_context(text, max_chars=2000):
        """Truncate context to fit within token limits."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars-3] + "..."


__all__ = ["PromptTemplates"]
