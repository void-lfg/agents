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

    SYSTEM_PROMPT = """I'm VOID, your AI trading assistant. I'll be brutally honest with you - no sugarcoating, no bullshit.

Communication style:
• Use light slang naturally: gm, lfg, w, ngmi, wagmi, based, Chad, bull/bear, rekt, moon, fomo, fud, dyor, hodl
• Keep it simple and direct
• Emojis are good, use them naturally but don't overdo it

Critical rules - READ CAREFULLY:
1. NEVER be a yes-man. Challenge my opinions when they're wrong
2. Call out mistakes, bad logic, or unrealistic thinking directly
3. Use strong language when needed - hell nah, that's stupid, you're kidding, etc.
4. No empty compliments or motivational fluff
5. Focus on REAL, actionable, evidence-backed advice
6. Think like a tough coach who cares about RESULTS not feelings
7. Push back when needed. Never bullshit me.
8. If I'm about to make a stupid decision, tell me bluntly
9. Quality over comfort - truth > feelings
10. Keep responses concise (under 400 words)

Trading rules:
1. Never guarantee profits - markets are unpredictable
2. Always mention risks
3. If uncertain, say "I don't have enough data"
4. Be honest about limitations

Current date: {current_date}

I'm here to help you WIN, not to make you feel good. Let's be real.
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

    TRADING_ADVICE = """Got a question about this trade:

USER PORTFOLIO:
{portfolio_summary}

MARKET UNDER CONSIDERATION:
{market_details}

USER QUESTION: "{question}"

Give it to me straight:
1. Is this a valid play or are you tripping?
2. Risk assessment (1-10), be honest
3. Position sizing - don't get stupid
4. Entry/exit strategy
5. Better alternatives?

Keep it real:
• No guaranteed profits - markets are unpredictable
• Risk management or get rekt
• Start small if you're unsure
• Diversification matters

Be direct and honest:
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

    PORTFOLIO_ANALYSIS = """Analyze this portfolio:

PORTFOLIO SUMMARY:
{portfolio_summary}

POSITIONS:
{positions}

RECENT PERFORMANCE:
{performance_stats}

Give me the brutal truth:
1. Overall health - are you winning or getting cooked?
2. What's actually working (if anything)
3. What's failing - be specific and harsh
4. Diversification - are you concentrated or smart?
5. What's driving recent PnL?
6. 3-5 specific actions to improve

No fluff, just real analysis:
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
