"""Persistent SQLite leases prevent duplicate jobs across API workers."""
import asyncio
import os
from src.api.news_refresh import acquire_job, finish_job, refresh_news
from src.api.watches import check_watches

async def background_loop():
    while True:
        for name, interval, operation in (
            ('news', max(300, int(os.getenv('NEWS_REFRESH_SECONDS', '21600'))), refresh_news),
            ('watches', max(60, int(os.getenv('WATCH_CHECK_SECONDS', '1800'))), check_watches),
        ):
            if await asyncio.to_thread(acquire_job, name, interval, 3600):
                try:
                    details = await asyncio.to_thread(operation)
                    await asyncio.to_thread(finish_job, name, details, not details.get('failed'))
                except Exception as exc:
                    await asyncio.to_thread(finish_job, name, {'error': str(exc)}, False)
        await asyncio.sleep(60)
