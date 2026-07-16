"""
Example script demonstrating AgentRails blocking "jailbreaks" and 
structurally unsound trades, providing feedback loops for an LLM.
"""

from agentrails import (
    AccountState, GuardrailConfig, GuardrailError,
    OrderSide, PlannedOrder, TradePlan, validate_plan
)

# A strict production config
config = GuardrailConfig(
    account_id="00000000",
    allowed_symbols={"VOO", "QQQ"},
    allow_sells=False,
    dry_run=True,
    max_order_usd=150,
    weekly_cap_usd=500,
    human_approval_threshold_usd=100.0,
    require_stop_loss_for_buys=True,
    max_position_concentration=0.40,  # No position > 40% of equity
)

account = AccountState(
    account_id="00000000", 
    buying_power=1000.0, 
    positions={"VOO": 400.0}
)

def run_scenario(scenario_name: str, orders: list[PlannedOrder], use_shadow_mode: bool = False):
    print(f"--- SCENARIO: {scenario_name} ---")
    config.shadow_mode = use_shadow_mode
    plan = TradePlan(
        account_id="00000000",
        generated_for="jailbreak-test",
        dry_run=True,
        orders=orders
    )
    
    # If in shadow mode, validate_plan returns a list of errors
    if use_shadow_mode:
        errors = validate_plan(plan, config, account)
        if errors:
            print(f"[SHADOW MODE] Caught {len(errors)} violations but allowed execution.")
            for e in errors:
                print(f"  - {e.message}")
        else:
            print("[SHADOW MODE] Plan is completely clean.")
        print()
        return

    # Normal mode: validate_plan raises GuardrailError
    try:
        validate_plan(plan, config, account)
        print("✅ SUCCESS: Plan passed all guardrails.\n")
    except GuardrailError as e:
        if e.requires_human_approval:
            print(f"⏸️  BLOCKED (Human Approval Required): {e.message}")
            print("Webhook sent to Telegram for confirmation...\n")
        else:
            print(f"❌ BLOCKED (Security Violation):")
            # This is what you would send back to the LLM
            print(e.to_feedback_prompt())
            print()

# 1. Jailbreak attempt: Buy an unapproved meme stock
run_scenario("Buy GameStop", [
    PlannedOrder("GME", OrderSide.BUY, 50, reason="To the moon!", stop_loss_price=40)
])

# 2. Structural failure: Buy without a stop-loss
run_scenario("Buy without stop-loss", [
    PlannedOrder("QQQ", OrderSide.BUY, 50, reason="Weekly DCA")
])

# 3. Budget failure: Exceed max position concentration
run_scenario("YOLO into VOO (Concentration Violation)", [
    # Equity = 1000 cash + 400 VOO = 1400. Max VOO allowed = 560.
    # Currently have 400, so can only buy 160 more. Attempting to buy 200.
    PlannedOrder("VOO", OrderSide.BUY, 200, stop_loss_price=400)
])

# 4. Human Approval requirement
run_scenario("Large allowed order (Requires Human)", [
    # 120 is < max_order (150) and < concentration limit (160), 
    # but > human threshold (100)
    PlannedOrder("VOO", OrderSide.BUY, 120, stop_loss_price=400)
])

# 5. Perfect, safe order
run_scenario("Safe standard order", [
    PlannedOrder("QQQ", OrderSide.BUY, 50, stop_loss_price=450)
])

# 6. Shadow mode test on a bad order
run_scenario("Shadow Mode - Buy AMC", [
    PlannedOrder("AMC", OrderSide.BUY, 50, stop_loss_price=10)
], use_shadow_mode=True)
