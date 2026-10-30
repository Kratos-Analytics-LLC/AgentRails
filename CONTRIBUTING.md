# Contributing to AgentRails

Thanks for your interest. AgentRails is a small, dependency-free Python library, and we want to keep it that way.

## Setup

```bash
git clone https://github.com/Kratos-Analytics-LLC/AgentRails.git
cd AgentRails
pip install -e ".[dev]"
pytest
```

Requires Python 3.10+. CI runs the test suite on Python 3.10–3.13, so please make sure `pytest` passes before you open a pull request.

## What fits

- Bug fixes in the core validator, ledger, circuit breaker or declarative policy loader.
- New reference adapters for other domains (see "Write your own adapter" in the README).
- Tests, examples and documentation improvements.

## What doesn't

AgentRails is deliberately not an agent, a strategy, or an SDK client. Please read "What's deliberately NOT in scope" in the README before proposing a feature. The core must stay domain-agnostic, dependency-free and unit-testable.

## Pull requests

1. Open an issue first for anything larger than a small fix, so we can agree on scope.
2. Keep changes focused; add or update tests for any behavior change.
3. Policy validation fails closed. A change that makes a policy more permissive by default needs a clear justification.

## Security

Please do not open public issues for vulnerabilities. See `SECURITY.md` for the trust boundary and how to report a problem, or write to kratosanalyticsllc@gmail.com.

## Contact

Kratos Analytics LLC — kratosanalyticsllc@gmail.com
