"""Immutable trip receipts, with real Solana devnet transaction verification.

Only a salted digest goes on chain. Coordinates and results remain private.
Wallet signing happens in the browser; this service never holds wallet keys.
"""
import hashlib
import json
import os
import secrets
from contextlib import contextmanager
import sqlite3
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth import get_current_user
from src.api.db import get_conn, get_trip_history_row

MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
RPC = os.getenv("SOLANA_DEVNET_RPC_URL", "https://api.devnet.solana.com")
receipt_router = APIRouter(prefix="/api/receipts", tags=["receipts"])


@contextmanager
def connection():
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS risk_receipts (
        id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
        trip_id INTEGER NOT NULL UNIQUE REFERENCES trip_history(id) ON DELETE CASCADE,
        canonical TEXT NOT NULL, digest TEXT NOT NULL,
        signature TEXT UNIQUE, wallet TEXT, verified_at TEXT
    )""")
    conn.commit()
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(risk_receipts)')}
    for name, kind in [('pending_signature', 'TEXT'), ('pending_wallet', 'TEXT'), ('last_valid_height', 'INTEGER')]:
        if name not in columns: conn.execute(f'ALTER TABLE risk_receipts ADD COLUMN {name} {kind}')
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def rpc(method, params):
    try:
        response = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1,
                                 "method": method, "params": params}, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise ValueError("RPC error")
        return data.get("result")
    except (requests.RequestException, ValueError):
        raise HTTPException(503, "Solana devnet chưa phản hồi. Hãy thử xác minh lại.")


def public(row):
    digest = hashlib.sha256(row["canonical"].encode("utf-8")).hexdigest()
    return {"id": row["id"], "canonical": row["canonical"], "sha256": row["digest"],
            "integrity": secrets.compare_digest(digest, row["digest"]),
            "memo": f"travelshield:v1:{row['id']}:{row['digest']}",
            "network": "devnet", "signature": row["signature"], "wallet": row["wallet"],
            "verified_at": row["verified_at"],
            "pending_signature": row['pending_signature'], "pending_wallet": row['pending_wallet'],
            "last_valid_height": row['last_valid_height'],
            "explorer_url": f"https://explorer.solana.com/tx/{row['signature']}?cluster=devnet" if row["signature"] else None}


@receipt_router.post("/trips/{trip_id}")
def issue(trip_id: int, user=Depends(get_current_user)):
    trip = get_trip_history_row(trip_id, user["id"])
    if not trip:
        raise HTTPException(404, "Không tìm thấy chuyến đi trong tài khoản.")
    with connection() as conn:
        row = conn.execute("SELECT * FROM risk_receipts WHERE trip_id=?", (trip_id,)).fetchone()
        if not row:
            receipt_id = secrets.token_hex(16)
            canonical = json.dumps({"schema": "travelshield.risk.v1", "id": receipt_id,
                "nonce": secrets.token_hex(32), "issued_at": datetime.now(timezone.utc).isoformat(),
                "assessed_at": json.loads(trip["result_json"]).get("assessed_at", trip["created_at"]), "result": json.loads(trip["result_json"])},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            conn.execute("INSERT OR IGNORE INTO risk_receipts (id,user_id,trip_id,canonical,digest) VALUES (?,?,?,?,?)",
                         (receipt_id, user["id"], trip_id, canonical, hashlib.sha256(canonical.encode()).hexdigest()))
            row = conn.execute("SELECT * FROM risk_receipts WHERE trip_id=?", (trip_id,)).fetchone()
        return public(row)


class VerifyPayload(BaseModel):
    signature: str = Field(min_length=80, max_length=90, pattern=r"^[1-9A-HJ-NP-Za-km-z]+$")
    wallet: str = Field(min_length=32, max_length=44, pattern=r"^[1-9A-HJ-NP-Za-km-z]+$")

class SubmissionPayload(VerifyPayload):
    last_valid_height: int = Field(gt=0)

@receipt_router.post('/{receipt_id}/submitted')
def submitted(receipt_id: str, payload: SubmissionPayload, user=Depends(get_current_user)):
    with connection() as conn:
        row = conn.execute('SELECT * FROM risk_receipts WHERE id=? AND user_id=?', (receipt_id, user['id'])).fetchone()
        if not row: raise HTTPException(404, 'Không tìm thấy bằng chứng.')
        if row['signature']: return public(row)
        if row['pending_signature'] and row['pending_signature'] != payload.signature:
            raise HTTPException(409, 'Cần kiểm tra giao dịch trước khi gửi lại.')
        conn.execute('UPDATE risk_receipts SET pending_signature=?,pending_wallet=?,last_valid_height=? WHERE id=?',
                     (payload.signature, payload.wallet, payload.last_valid_height, receipt_id))
        return public(conn.execute('SELECT * FROM risk_receipts WHERE id=?', (receipt_id,)).fetchone())

@receipt_router.post('/{receipt_id}/recover')
def recover(receipt_id: str, user=Depends(get_current_user)):
    with connection() as conn:
        row = conn.execute('SELECT * FROM risk_receipts WHERE id=? AND user_id=?', (receipt_id, user['id'])).fetchone()
        if not row: raise HTTPException(404, 'Không tìm thấy bằng chứng.')
        if row['signature']: return {**public(row), 'transaction_state': 'confirmed'}
        if not row['pending_signature']: return {**public(row), 'transaction_state': 'not_sent'}
        if rpc('getGenesisHash', []) != 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG':
            raise HTTPException(503, 'RPC phải kết nối devnet.')
        result = rpc('getSignatureStatuses', [[row['pending_signature']], {'searchTransactionHistory': True}])
        state = (result.get('value') or [None])[0] if result else None
        if state and not state.get('err') and state.get('confirmationStatus') in ('confirmed', 'finalized'):
            return {**public(row), 'transaction_state': 'ready_to_verify'}
        failed = bool(state and state.get('err'))
        expired = not state and rpc('getBlockHeight', [{'commitment': 'confirmed'}]) > row['last_valid_height']
        if failed or expired:
            conn.execute('UPDATE risk_receipts SET pending_signature=NULL,pending_wallet=NULL,last_valid_height=NULL WHERE id=?', (receipt_id,))
            return {**public(conn.execute('SELECT * FROM risk_receipts WHERE id=?', (receipt_id,)).fetchone()),
                    'transaction_state': 'failed' if failed else 'expired'}
        return {**public(row), 'transaction_state': 'pending'}


@receipt_router.post("/{receipt_id}/verify")
def verify(receipt_id: str, payload: VerifyPayload, user=Depends(get_current_user)):
    with connection() as conn:
        row = conn.execute("SELECT * FROM risk_receipts WHERE id=? AND user_id=?", (receipt_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy bằng chứng.")
        receipt = public(row)
        if not receipt["integrity"]:
            raise HTTPException(409, "Nội dung bằng chứng không còn khớp hash.")
        if row["signature"] and (row["signature"] != payload.signature or row["wallet"] != payload.wallet):
            raise HTTPException(409, "Bằng chứng đã gắn với một giao dịch khác.")
        if rpc("getGenesisHash", []) != "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG":
            raise HTTPException(503, "RPC phải kết nối Solana devnet.")
        tx = rpc("getTransaction", [payload.signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
        if not tx:
            raise HTTPException(409, "Giao dịch chưa được xác nhận. Hãy thử lại.")
        if not tx.get("meta") or tx["meta"].get("err") is not None:
            raise HTTPException(422, "Giao dịch không thành công.")
        message = tx["transaction"]["message"]
        signers = [k["pubkey"] for k in message["accountKeys"] if isinstance(k, dict) and k.get("signer")]
        memos = [i.get("parsed") for i in message["instructions"] if i.get("programId") == MEMO_PROGRAM]
        if payload.wallet not in signers or receipt["memo"] not in memos:
            raise HTTPException(422, "Ví hoặc nội dung giao dịch không khớp bằng chứng.")
        try:
            updated = conn.execute("UPDATE risk_receipts SET signature=?,wallet=?,verified_at=?,pending_signature=NULL,pending_wallet=NULL,last_valid_height=NULL WHERE id=? AND (signature IS NULL OR (signature=? AND wallet=?))",
                         (payload.signature, payload.wallet, datetime.now(timezone.utc).isoformat(), receipt_id, payload.signature, payload.wallet))
            if not updated.rowcount:
                raise HTTPException(409, "Bằng chứng đã được xác minh bằng giao dịch khác.")
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Giao dịch đã được dùng cho một bằng chứng khác.")
        return public(conn.execute("SELECT * FROM risk_receipts WHERE id=?", (receipt_id,)).fetchone())
