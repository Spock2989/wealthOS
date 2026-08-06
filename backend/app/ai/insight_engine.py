from app.ai.client import call_llm, DEFAULT_MODEL
import dataclasses, json

class InsightEngine:
    def generate(self, data):
        if hasattr(data, "__dataclass_fields__"):
            d = json.dumps(dataclasses.asdict(data), default=str, indent=2)[:6000]
        else:
            d = str(data)[:6000]

        summary_prompt = f"""You are a senior SEBI-registered wealth advisor writing for another advisor reviewing a client portfolio. Based on the analytics below, write a detailed portfolio summary in 4 sections:

**1. Portfolio Composition**
Cover total AUM in rupees, number of holdings, asset class breakdown with exact percentages, sector exposure highlights, and market cap distribution. Be specific.

**2. Strengths**
Identify 3 specific strengths with numbers (e.g. diversification score, low concentration, sector balance).

**3. Concerns**
Identify 3 specific concerns with numbers (e.g. concentration risks, sector overweight, liquidity, fund overlap).

**4. Overall Assessment**
Give a 2-sentence verdict on portfolio health and a grade out of 10.

Use rupee symbols, percentages, and exact figures throughout. Avoid generic statements. Write for a sophisticated advisor, not a retail client.

Analytics JSON:
{d}"""

        meeting_prompt = f"""You are a wealth advisor preparing for a client meeting. Based on the portfolio analytics below, generate detailed meeting prep notes in this structure:

**Client Profile Recap** (2 lines)
**Key Talking Points** (5 specific points with numbers)
**Questions to Ask the Client** (4 questions)
**Action Items to Propose** (3 specific rebalancing or review suggestions with rationale)
**Red Flags to Address** (any concentration, stress, or liquidity concerns)

Be specific with rupee amounts, percentages, scenario impacts. Each point should be actionable. Write in a professional advisor tone.

Analytics JSON:
{d}"""

        risk_prompt = f"""You are a risk analyst at an Indian wealth firm. Write a comprehensive risk commentary covering these areas in detail:

**1. Concentration and Market Risk Assessment** (1 paragraph with HHI, top holdings %, sector concentration)
**2. Stress Testing and Downside Risk Exposure** (1 paragraph covering worst-case scenarios with rupee impact)
**3. Liquidity and Drawdown Vulnerability** (1 paragraph on liquidity profile and historical drawdown sensitivity)
**4. Volatility and Factor Risks** (1 paragraph on volatility band, market cap risks, fund overlap)
**5. Mitigation Recommendations** (3 specific risk mitigation actions)

Use exact numbers from the analytics throughout. Reference specific scenarios (RBI rate hike, US recession, stagflation, etc) where relevant. Write at institutional risk-analyst quality.

Analytics JSON:
{d}"""

        # Pass the model explicitly and report that same variable, so the
        # stored report can never claim a model that did not produce it.
        # This previously hardcoded "claude-sonnet-4-20250514" while call_llm
        # actually ran Haiku — a false provenance label on a persisted record.
        model = DEFAULT_MODEL

        s = call_llm(summary_prompt, model=model)
        m = call_llm(meeting_prompt, model=model)
        r = call_llm(risk_prompt, model=model)

        return {
            "portfolio_summary": s,
            "meeting_prep_notes": m,
            "risk_commentary": r,
            "ai_provider": "claude",
            "model": model,
        }
