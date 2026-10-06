import hashlib
import json

from src.api.db import save_trip_history
from src.api import receipts


def create(client, headers):
    user = client.get('/api/auth/me', headers=headers).json()
    trip_id = save_trip_history(user['id'], 'Đà Lạt', 10, 106, 'solo', {
        'to': {'name': 'Đà Lạt'}, 'risk': {'data_status': 'stale'},
        'weather': {'risk_score': 3}, 'recommendation': 'CAUTION'})
    response = client.post(f'/api/receipts/trips/{trip_id}', headers=headers)
    assert response.status_code == 200
    return trip_id, response.json()


def test_immutable_private_receipt(client, auth_headers):
    trip_id, receipt = create(client, auth_headers)
    repeated = client.post(f'/api/receipts/trips/{trip_id}', headers=auth_headers).json()
    assert repeated == receipt
    assert hashlib.sha256(receipt['canonical'].encode()).hexdigest() == receipt['sha256']
    assert 'Đà Lạt' not in receipt['memo']
    assert json.loads(receipt['canonical'])['result']['risk']['data_status'] == 'stale'
    assert receipt['signature'] is None
    assert client.post(f'/api/receipts/trips/{trip_id}').status_code == 401
    other = client.post('/api/auth/register', json={'email': f"other-{receipt['id']}@example.com", 'password': 'testpass123'}).json()
    assert client.post(f'/api/receipts/trips/{trip_id}', headers={'Authorization': f"Bearer {other['token']}"}).status_code == 404


def test_chain_verification_rejects_wrong_memo_and_signer(client, auth_headers, monkeypatch):
    _, receipt = create(client, auth_headers)
    payload = {'signature': '2' * 88, 'wallet': '3' * 44}
    tx = {'meta': {'err': None}, 'transaction': {'message': {
        'accountKeys': [{'pubkey': payload['wallet'], 'signer': True}],
        'instructions': [{'programId': receipts.MEMO_PROGRAM, 'parsed': 'wrong'}]}}}
    monkeypatch.setattr(receipts, 'rpc', lambda method, params: 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG' if method == 'getGenesisHash' else tx)
    url = f"/api/receipts/{receipt['id']}/verify"
    assert client.post(url, json=payload, headers=auth_headers).status_code == 422
    tx['transaction']['message']['instructions'][0]['parsed'] = receipt['memo']
    tx['transaction']['message']['accountKeys'][0]['signer'] = False
    assert client.post(url, json=payload, headers=auth_headers).status_code == 422
    tx['transaction']['message']['accountKeys'][0]['signer'] = True
    response = client.post(url, json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()['verified_at']
    assert response.json()['signature'] == payload['signature']


def test_chain_pending_failed_and_tampering(client, auth_headers, monkeypatch):
    _, receipt = create(client, auth_headers)
    url = f"/api/receipts/{receipt['id']}/verify"
    payload = {'signature': '4' * 88, 'wallet': '5' * 44}
    monkeypatch.setattr(receipts, 'rpc', lambda method, params: 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG' if method == 'getGenesisHash' else None)
    assert client.post(url, json=payload, headers=auth_headers).status_code == 409
    monkeypatch.setattr(receipts, 'rpc', lambda method, params: 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG' if method == 'getGenesisHash' else {'meta': {'err': {'failed': True}}})
    assert client.post(url, json=payload, headers=auth_headers).status_code == 422
    with receipts.connection() as conn:
        conn.execute('UPDATE risk_receipts SET canonical=? WHERE id=?', ('tampered', receipt['id']))
    assert client.post(url, json=payload, headers=auth_headers).status_code == 409


def test_delete_trip_removes_private_receipt(client, auth_headers):
    trip_id, receipt = create(client, auth_headers)
    assert client.delete(f'/api/trip-history/{trip_id}', headers=auth_headers).status_code == 200
    assert client.post(f'/api/receipts/trips/{trip_id}', headers=auth_headers).status_code == 404
    with receipts.connection() as conn:
        assert conn.execute('SELECT * FROM risk_receipts WHERE id=?', (receipt['id'],)).fetchone() is None
