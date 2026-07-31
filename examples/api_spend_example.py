"""Reference integration: putting a spend cap around an autonomous agent that
calls paid APIs (LLM providers, search, etc.).

Like the trading example, this is illustrative, not runnable as-is —
`call_paid_api` stands in for whatever your agent framework uses to actually
hit the provider. The point being demonstrated is the CONTROL FLOW, which is
identical in shape to the trading example even though nothing here is financial:

    1. Load how much of today's budget is already spent (SpendState).
    2. Run YOUR agent logic to produce an ApiCallPlan (not shown — bring yours).
    3. validate_api_spend() — hard stop on any spend-policy violation.
    4. Check the circuit breaker — hard stop if too many recent calls failed.
    5. If dry_run: print the summary and log it, then stop. Otherwise make each
       call, record the real cost to the ledger, and feed failures to the breaker.

Same library, same core, second domain — that's the whole Phase 2 point.
"""

from __future__ import annotations

from agentrails import CircuitBreaker, Ledger, PolicyError
from agentrails.adapters.api_spend import (
    ApiCall,
    ApiCallPlan,
    SpendPolicy,
    SpendState,
    summarize_plan,
    validate_api_spend,
)

# ---------------------------------------------------------------------------
# 1. Policy lives in one place, reviewed like code (not edited on a whim).
# ---------------------------------------------------------------------------

POLICY = SpendPolicy(
    run_id="research-agent",
    allowed_providers={"anthropic", "openai"},
    allowed_models={"claude-opus-4-8", "claude-haiku-4-5", "gpt-5"},
    dry_run=True,  # flip to False only after you trust the plan output
    max_call_usd=1.00,
    max_calls_per_run=20,
    per_run_budget_usd=5.00,  # cap for one run; the daily cap lives in SpendState
    human_approval_threshold_usd=2.00,
    max_provider_concentration=0.90,
)

LEDGER = Ledger("reports/api_spend_ledger.csv")
# The circuit breaker is cross-cutting; here we use its generic "N consecutive
# failures" mode to pause an agent that keeps hitting API errors. The drawdown
# axis (update_value) doesn't apply to spend, so we leave it effectively off.
BREAKER = CircuitBreaker(
    "reports/api_breaker.json",
    max_consecutive_failures=5,  # 5 failed calls in a row -> pause
    max_drawdown_pct=1.0,
    cooldown_hours=1,
)


def call_paid_api(provider: str, model: str, **kwargs) -> dict:
    """Stand-in for your agent's actual API call. Replace with the real client
    (Anthropic/OpenAI SDK, etc.). AgentRails never calls this itself; that's on
    purpose — it tells you whether you're allowed to, you make the call."""
    raise NotImplementedError("wire this up to your API client")


def load_spend_state() -> SpendState:
    """Where you track today's spend so a cold, scheduled run still respects the
    daily cap. Back it with the ledger, a state file, or your billing API."""
    return SpendState(
        run_id="research-agent",
        daily_budget_usd=20.00,
        spent_today_usd=0.00,  # read this from your ledger/state store
    )


def build_plan_with_your_agent(state: SpendState) -> ApiCallPlan:
    """The one function AgentRails deliberately does NOT provide: your agent's
    own logic decides which calls it wants to make. AgentRails' job starts the
    moment you have an ApiCallPlan."""
    raise NotImplementedError("bring your own agent logic")


def run() -> None:
    if BREAKER.is_tripped():
        print(f"Circuit breaker tripped ({BREAKER.state.reason}); skipping this run.")
        return

    state = load_spend_state()
    plan = build_plan_with_your_agent(state)

    try:
        validate_api_spend(plan, POLICY, state)
    except PolicyError as e:
        LEDGER.record_action(
            scope_id=POLICY.run_id,
            run_label=plan.generated_for,
            target=e.target or "-",
            action_type="call",
            cost=plan.cost_total,
            status="rejected",
            note=e.message,
        )
        # If it needs a human rather than being forbidden, route it for sign-off.
        if e.requires_human_approval:
            print(f"Needs human approval before spending: {e}")
        else:
            print(f"Spend policy violation, nothing called: {e}")
            print(e.to_feedback_prompt())  # hand back to the planner to revise
        return

    if plan.dry_run:
        print(summarize_plan(plan))
        for c in plan.calls:
            LEDGER.record_action(
                scope_id=POLICY.run_id,
                run_label=plan.generated_for,
                target=c.provider,
                action_type=c.call_type,
                cost=c.est_cost_usd,
                status="dry_run",
                note=c.reason,
            )
        return

    for c in plan.calls:
        try:
            result = call_paid_api(c.provider, c.model, tag=c.tag)
        except Exception as exc:  # a real failure, not a policy rejection
            BREAKER.record_failure()  # grows the streak; trips on the Nth in a row
            LEDGER.record_action(
                scope_id=POLICY.run_id,
                run_label=plan.generated_for,
                target=c.provider,
                action_type=c.call_type,
                cost=0.0,
                status="rejected",
                note=f"api error: {exc}",
            )
            continue

        BREAKER.record_success()  # resets the failure streak
        LEDGER.record_action(
            scope_id=POLICY.run_id,
            run_label=plan.generated_for,
            target=c.provider,
            action_type=c.call_type,
            cost=result.get("cost_usd", c.est_cost_usd),
            status="filled",
            ref_id=result.get("id", ""),
            note=c.reason,
        )


if __name__ == "__main__":
    run()
