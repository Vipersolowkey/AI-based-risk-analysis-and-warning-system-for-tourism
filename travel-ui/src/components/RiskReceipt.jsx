import { useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { apiPost } from '../api';

export default function RiskReceipt({ tripId, token }) {
  const [receipt, setReceipt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const storageKey = `travelshield-receipt-${tripId}`;
  async function execute(publish) {
    setBusy(true); setError('');
    try {
      let current = await apiPost(`/api/receipts/trips/${tripId}`, {}, token);
      const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(current.canonical)));
      const digest = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
      if (digest !== current.sha256 || !current.integrity) throw new Error('Bằng chứng không khớp nội dung đã lưu.');
      setReceipt(current);
      let saved = null;
      try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch { /* A corrupt local cache must not block receipt retrieval. */ }
      let pending = current.signature ? { signature: current.signature, wallet: current.wallet } : saved?.id === current.id ? saved : null;
      if (publish && !pending) {
        const wallet = window.phantom?.solana || window.solana;
        if (!wallet?.signAndSendTransaction) throw new Error('Hãy dùng trình duyệt có ví Solana (Phantom), rồi thử lại.');
        const { Connection, Transaction, TransactionInstruction, PublicKey } = await import('@solana/web3.js');
        const account = await wallet.connect();
        const connection = new Connection(import.meta.env.VITE_SOLANA_DEVNET_RPC_URL || 'https://api.devnet.solana.com', 'confirmed');
        if (await connection.getGenesisHash() !== 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG') throw new Error('RPC phải kết nối Solana devnet.');
        const block = await connection.getLatestBlockhash();
        const transaction = new Transaction({ feePayer: account.publicKey, ...block });
        transaction.add(new TransactionInstruction({
          programId: new PublicKey('MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr'),
          keys: [{ pubkey: account.publicKey, isSigner: true, isWritable: false }],
          data: new TextEncoder().encode(current.memo),
        }));
        const sent = await wallet.signAndSendTransaction(transaction);
        pending = { id: current.id, signature: sent.signature, wallet: account.publicKey.toBase58() };
        localStorage.setItem(storageKey, JSON.stringify(pending));
        setReceipt({ ...current, ...pending });
        const confirmation = await connection.confirmTransaction({ ...block, signature: pending.signature }, 'confirmed');
        if (confirmation.value.err) throw new Error('Giao dịch thất bại. Hãy kiểm tra trên Explorer.');
      }
      if (pending) {
        current = await apiPost(`/api/receipts/${current.id}/verify`, { signature: pending.signature, wallet: pending.wallet }, token);
        setReceipt(current);
      }
    } catch (err) { setError(err.message || 'Chưa xác minh được. Hãy thử lại.'); }
    finally { setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `travelshield-${receipt.id}.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <Box className="portal-section">
    <Typography variant="h3" component="h2">Bằng chứng đánh giá chuyến đi</Typography>
    <Typography color="text.secondary" sx={{ my: 1 }}>Lưu dấu nội dung đánh giá để đối chiếu về sau. Chỉ mã băm được công khai trên Solana devnet; vị trí và chi tiết chuyến đi nằm trong tài khoản của bạn. Bằng chứng xác nhận nội dung đã ghi, không chứng nhận chuyến đi an toàn.</Typography>
    {!tripId && <Alert severity="info">Đánh giá lại khi đã đăng nhập để tạo bằng chứng.</Alert>}
    {error && <Alert severity="error" sx={{ my: 1 }}>{error}</Alert>}
    {receipt && <Alert severity={receipt.verified_at ? 'success' : 'info'} sx={{ my: 1 }}>{receipt.verified_at ? 'Đã xác minh nội dung và ví ký trên Solana devnet.' : 'Đã lưu bằng chứng riêng tư. Chưa xác minh trên blockchain.'}</Alert>}
    {receipt && <Typography variant="body2" sx={{ overflowWrap: 'anywhere', my: 1 }}>SHA-256: {receipt.sha256}</Typography>}
    <Stack direction="row" flexWrap="wrap" gap={1}>
      <Button disabled={busy || !tripId || !token} onClick={() => execute(false)} variant="outlined">{busy ? 'Đang xử lý…' : 'Tải / xác minh lại'}</Button>
      <Button disabled={busy || !tripId || !token || Boolean(receipt?.verified_at)} onClick={() => execute(true)} variant="contained">Ghi bằng chứng lên Solana devnet</Button>
      {receipt && <Button onClick={download}>Tải bằng chứng JSON</Button>}
      {receipt?.signature && <Button component="a" href={`https://explorer.solana.com/tx/${receipt.signature}?cluster=devnet`} target="_blank" rel="noopener noreferrer">Xem giao dịch</Button>}
    </Stack>
    <Typography variant="caption" color="text.secondary">Chuyển ví sang devnet trước khi ký. Phí dùng SOL thử nghiệm.</Typography>
  </Box>;
}
