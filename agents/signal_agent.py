"""Combines news sentiment and technical analysis into a final trading signal."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Signal:
    ticker: str
    recommendation: str          # "buy" | "sell" | "hold" | "watch"
    confidence: float            # 0.0 – 1.0
    sentiment: str               # from NewsAgent
    technical_signal: str        # from StockAgent
    price_change_pct: float
    themes: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict:
        return self.__dict__


class SignalAgent:
    """Merges NewsAgent output and StockAgent output into an actionable Signal."""

    # Weights for blending sentiment and technical scores
    _SENTIMENT_WEIGHT = 0.45
    _TECHNICAL_WEIGHT = 0.55

    _SENTIMENT_SCORE = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}
    _TECHNICAL_SCORE = {"buy": 1.0, "hold": 0.5, "sell": 0.0, "insufficient_data": 0.5}

    def generate(self, ticker: str, news_analysis: dict, stock_analysis: dict) -> Signal:
        sentiment = news_analysis.get("sentiment", "neutral")
        technical = stock_analysis.get("signal", "hold")
        news_confidence = float(news_analysis.get("confidence", 0.5))

        s_score = self._SENTIMENT_SCORE.get(sentiment, 0.5)
        t_score = self._TECHNICAL_SCORE.get(technical, 0.5)
        blended = (s_score * self._SENTIMENT_WEIGHT + t_score * self._TECHNICAL_WEIGHT)
        confidence = round((blended + news_confidence) / 2, 2)

        if blended >= 0.70:
            recommendation = "buy"
        elif blended <= 0.35:
            recommendation = "sell"
        elif 0.45 <= blended < 0.55:
            recommendation = "watch"
        else:
            recommendation = "hold"

        return Signal(
            ticker=ticker,
            recommendation=recommendation,
            confidence=confidence,
            sentiment=sentiment,
            technical_signal=technical,
            price_change_pct=stock_analysis.get("price_change_pct", 0.0),
            themes=news_analysis.get("themes", []),
            risk_factors=news_analysis.get("risk_factors", []),
            summary=news_analysis.get("summary", ""),
        )
