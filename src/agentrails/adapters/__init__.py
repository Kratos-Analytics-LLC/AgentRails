"""Domain adapters that map a concrete domain onto the generic AgentRails core.

Each adapter translates its domain objects into `agentrails.core` primitives
(Action / ActionPlan / Policy / PolicyContext), so the same generic validator
protects any kind of agent action.

Three reference adapters ship today, on purpose from very different domains, to
show the core is genuinely generic and not just trading with new labels:

    trading    — cap a broker trade plan   (cost axis = dollars per order)
    api_spend  — cap an agent's API budget  (cost axis = dollars per call)
    shell      — gate command execution     (cost axis barely used; the star is
                 reversible=False for rm -rf / git push --force / DROP TABLE)

Writing a fourth (email sends, infra changes, ...) is the same recipe: map your
domain onto the four core primitives, then let `agentrails.core.validate_actions`
do the generic work while your adapter keeps whatever rule is genuinely
domain-specific.
"""
