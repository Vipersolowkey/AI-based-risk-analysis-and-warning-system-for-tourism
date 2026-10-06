# TravelShield — product delivery

## Working flow

Sign in → assess a trip → open Result → load a receipt → publish using your Solana wallet on devnet → verify through backend → revisit in History or download JSON.

Receipts use the server's saved trip result, not a browser-supplied risk score. One immutable receipt is issued per history entry. A random nonce protects the digest from guessing attacks. Only `travelshield:v1:<receipt-id>:<sha256>` is published in a signed Memo instruction. The server checks the devnet genesis, confirmed transaction success, exact memo and signer. A receipt proves a snapshot's integrity; it does not prove an AI prediction correct or a trip safe.

## Run

Backend: `pip install -r requirements.txt`, then `python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000`.

Frontend: in `travel-ui`, run `npm ci`, then `npm run dev -- --host 127.0.0.1`.

Open http://127.0.0.1:5173. Use Phantom with devnet selected and funded with test SOL. Signing remains in the wallet. No wallet private key is stored by TravelShield.

Configure `SOLANA_DEVNET_RPC_URL` on the backend and optionally `VITE_SOLANA_DEVNET_RPC_URL` on the frontend for your devnet RPC. Public RPC may rate-limit. A submitted signature is retained in this browser so a confirmation timeout can be retried without sending another transaction. A failed/expired submitted transaction requires investigation on Explorer; it is never marked verified automatically.

## Deployment requirements

Deploy the API and frontend, set `VITE_API_BASE_URL`, use a persistent SQLite volume, set a strong `JWT_SECRET`, configure SerpAPI if live traffic is desired and VAPID for push alerts. Keep provider credentials server-side. News remains an offline corpus until a fresh crawl and scoring pipeline is scheduled. PhoBERT is optional; do not describe it as the active model unless its artifact is installed.

The new receipt flow has not been deployed to the pre-existing public demo. Wallet signing and a funded devnet transaction must be checked on the deployment before calling the on-chain flow release-ready.

## Checks

Verified locally: real Da Lat trip assessment using XGBoost, private receipt creation, SHA-256 comparison, JSON download, history reopen, 390px mobile layout and no JavaScript exceptions. Devnet RPC connectivity was checked; public faucet returned an internal error, so a live funded transaction remains an explicit release check. Dependency audit after compatible updates has zero high/critical findings and four moderate transitive SDK findings (jayson/stream-json/uuid). These remain to be resolved before a production dependency sign-off.

`python -m pytest -q`; in `travel-ui`: `npm run build` and `npm run lint`.

Optional full local UI check: install Playwright in your tooling environment and run `node scripts/verify_receipt_e2e.cjs`. `PLAYWRIGHT_PATH` may point to the installed Playwright module. This registers a disposable QA account, assesses a real trip, checks receipt download, history, mobile layout and missing-wallet handling. Blockchain verification unit tests use controlled RPC responses; they are not evidence of a live transaction.
