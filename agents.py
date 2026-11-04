from .models import AgentAssessment
from .validation import validate_bars


class TemporalAnalyst:
    name = "temporal_analyst"

    def analyze(self, bars, portfolio):
        closes = validate_bars(bars)
        first, last = closes[0], closes[-1]
        total_return = last / first - 1.0
        returns = [(b / a) - 1.0 for a, b in zip(closes, closes[1:])]
        mean = sum(returns) / len(returns)
        variance = sum((x - mean) ** 2 for x in returns) / len(returns)
        volatility = variance ** 0.5
        short_start = closes[max(0, len(closes) - 4)]
        short_return = last / short_start - 1.0
        action = "BUY" if total_return > 0.01 and short_return >= 0 else (
            "SELL" if total_return < -0.01 and short_return <= 0 else "HOLD"
        )
        return AgentAssessment(
            self.name, action, min(0.8, abs(total_return) * 4 + 0.25),
            "Basic price-history trend and return-volatility assessment.",
            [f"Window return: {total_return:.4%}", f"Recent return: {short_return:.4%}"],
            ["A short price window cannot establish a durable market regime."],
            {"window_return": total_return, "recent_return": short_return,
             "return_volatility": volatility, "observations": len(closes)},
        )


class StrategicAnalyst:
    name = "strategic_analyst"

    def analyze(self, bars, portfolio):
        closes = validate_bars(bars)
        change = closes[-1] / closes[0] - 1.0
        action = "BUY" if change > 0.015 else ("SELL" if change < -0.015 else "HOLD")
        return AgentAssessment(
            self.name, action, 0.55,
            "Baseline strategy proposes a direction while preserving HOLD as the default.",
            [f"Observed window price change: {change:.4%}"],
            ["This simple rule is illustrative, not a validated trading strategy."],
            {"window_return": change, "alternatives": ["BUY", "SELL", "HOLD"]},
        )


class RiskAnalyst:
    name = "risk_analyst"

    def __init__(self, max_exposure_pct=20.0, max_drawdown_pct=10.0,
                 max_volatility=0.05):
        self.max_exposure_pct = float(max_exposure_pct)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.max_volatility = float(max_volatility)

    def analyze(self, bars, portfolio):
        closes = validate_bars(bars)
        returns = [(b / a) - 1.0 for a, b in zip(closes, closes[1:])]
        mean = sum(returns) / len(returns)
        vol = (sum((x - mean) ** 2 for x in returns) / len(returns)) ** 0.5
        exposure = float(portfolio.get("exposure_pct", 0.0))
        drawdown = float(portfolio.get("drawdown_pct", 0.0))
        violations = []
        if exposure > self.max_exposure_pct:
            violations.append("Current exposure exceeds configured maximum.")
        if drawdown > self.max_drawdown_pct:
            violations.append("Current drawdown exceeds configured maximum.")
        if vol > self.max_volatility:
            violations.append("Observed return volatility exceeds configured maximum.")
        safe = not violations
        return AgentAssessment(
            "risk_analyst", "HOLD", 0.95 if safe else 1.0,
            "Risk assessment; this agent never independently authorizes a trade.",
            [f"Exposure: {exposure:.3f}%", f"Drawdown: {drawdown:.3f}%",
             f"Observed return volatility: {vol:.5f}"],
            violations,
            {"risk_pass": safe, "exposure_pct": exposure,
             "drawdown_pct": drawdown, "return_volatility": vol,
             "max_exposure_pct": self.max_exposure_pct,
             "max_drawdown_pct": self.max_drawdown_pct,
             "max_volatility": self.max_volatility},
        )


class AdversarialAnalyst:
    name = "adversarial_analyst"

    def analyze(self, bars, portfolio):
        closes = validate_bars(bars)
        gaps = [abs(b / a - 1.0) for a, b in zip(closes, closes[1:])]
        largest = max(gaps)
        risks = ["Historical prices may omit spreads, fees, slippage, and market impact."]
        if largest > 0.05:
            risks.append("A price move above 5% exists in the input window; test gap risk.")
        if len(closes) < 10:
            risks.append("Fewer than 10 observations: evidence is too limited for strong conviction.")
        return AgentAssessment(
            self.name, "HOLD", 0.9,
            "Independent challenge of data sufficiency and strategy assumptions.",
            [f"Largest absolute one-step move: {largest:.4%}"],
            risks,
            {"largest_step_return": largest, "observations": len(closes)},
        )


class FeedbackAnalyst:
    name = "feedback_analyst"

    def analyze(self, forecast_action, forecast_price, realized_price):
        if forecast_action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("forecast_action must be BUY, SELL, or HOLD")
        if forecast_price <= 0 or realized_price <= 0:
            raise ValueError("prices must be positive")
        realized_return = realized_price / forecast_price - 1.0
        correct_direction = (
            (forecast_action == "BUY" and realized_return > 0) or
            (forecast_action == "SELL" and realized_return < 0) or
            (forecast_action == "HOLD" and abs(realized_return) < 0.005)
        )
        return AgentAssessment(
            self.name, "HOLD", 1.0,
            "Outcome review; records forecast direction versus realized movement.",
            [f"Realized return since forecast: {realized_return:.4%}"],
            [] if correct_direction else ["Forecast direction did not match the configured outcome test."],
            {"forecast_action": forecast_action, "realized_return": realized_return,
             "directional_hit": correct_direction},
        )
