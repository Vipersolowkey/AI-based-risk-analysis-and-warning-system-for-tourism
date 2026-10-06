# TravelShield QA snapshot

QA performed on 2026-10-05. This commit publishes the current implementation, not a completed production release.

## Passing checks

- Backend suite: 173 passed, 1 skipped.
- Frontend ESLint and production build passed.
- Local browser checks passed: trip result, receipt creation/hash, JSON download, history reopen, missing-wallet handling, and 390px mobile layout.
- Targeted checks passed for forecast date boundaries (today through +15 days), RSS deduplication with a mocked classifier, and persistent job lease exclusion.

## Known blockers

1. News model artifact was serialized with scikit-learn 1.8.0. Local runtime 1.7.2 raises `AttributeError: LogisticRegression has no attribute multi_class` during prediction; requirements currently pin 1.5.1. Align the artifact and runtime before enabling live news refresh.
2. The local API process used during QA still served the previous implementation. Restart and verify the new news, watches, receipt recovery and departure-date routes before end-to-end testing the new features.
3. Receipt recovery/submission endpoints exist, but the browser still uses local pending state and direct verification. Complete pending/failed/expired recovery and insufficient-SOL/wallet-rejection handling.
4. Watches compare against the immediately previous poll. Gradual risk increases (3.5 to 4 to 4.5 to 5) produce no alert. Use threshold crossings or a stable baseline.
5. Result/alerts UI is not yet wired to all new explanations/watch APIs and retains labels describing departure forecasts as current conditions. Local Web Push has no VAPID configuration.
6. No funded, wallet-signed live Solana devnet transaction or real Web Push delivery has been demonstrated. RPC/unit checks do not prove these live flows.

No production deployment of this snapshot has been verified. Preserve these caveats in submission descriptions.
