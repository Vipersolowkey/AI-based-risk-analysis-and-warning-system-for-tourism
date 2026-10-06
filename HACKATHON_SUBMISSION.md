# TravelShield AI

Track: Best AI Product. Product theme: AI x Web3.

## Product summary

TravelShield helps travelers in Vietnam prepare for a trip using weather AI, route information and dated news evidence. It explains when data is unavailable or stale. A private trip assessment can be anchored by its hash on Solana devnet and verified later against the wallet-signed transaction.

## Pitch outline

1. Problem: travelers compare weather, routes and local incidents across disconnected tools; incomplete evidence can look falsely reassuring.
2. Product: one trip assessment with Go/Caution/Don't Go, seven-day forecast, maps and source availability.
3. AI: XGBoost weather classifier plus explicit safety rules; offline Vietnamese news classifier and severity features. PhoBERT is an optional higher-capacity model, not a default deployed inference claim.
4. Web3: wallet-signed Memo instruction stores a salted SHA-256 commitment. Backend verifies confirmed devnet transaction success, exact memo and signer. No travel coordinates or risk details are published on chain.
5. Value and next steps: travelers can compare and revisit the evidence behind a recommendation; next milestones are refreshing news ingestion, user validation and production deployment.

## 2-minute demo sequence

- 0–15s: explain a trip decision and show TravelShield.
- 15–45s: assess a trip to Da Lat; inspect weather, route and data freshness.
- 45–65s: show seven-day forecast and map.
- 65–100s: load a private receipt, sign the Memo transaction in a devnet wallet, open the confirmed transaction, then verify in TravelShield.
- 100–120s: revisit the receipt in History and download the JSON.

## Honest release status

The local application and receipt UI have been exercised end to end. Unit tests exercise chain verification with controlled RPC results. A live devnet transaction still requires a funded devnet wallet (public faucet returned an internal error during QA). New receipt code is not yet on the existing public demo. Do not present a live chain confirmation or deployment as complete until those checks pass.

Use the actual submitted repository URL and working deployed URLs. Explain pre-existing functionality and hackathon additions separately, and credit contributors accurately. News data is an offline corpus; route estimates are distinct from live congestion. A receipt proves record integrity, not the accuracy of a safety recommendation.
