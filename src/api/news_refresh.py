"""Incremental RSS ingestion, headline inference and persistent refresh status."""
import hashlib
import html
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import joblib
import requests
import yaml
from fastapi import APIRouter
from src.api.db import get_conn
from src.api.config import PROJECT_ROOT
from src.nlp.risk_rules import build_risk_features
from src.nlp.provinces import match_province

news_router = APIRouter(prefix='/api/news', tags=['news'])

def init_news():
    conn = get_conn()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS live_news (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS background_jobs (
            name TEXT PRIMARY KEY, last_started REAL, last_success REAL,
            lease_until REAL NOT NULL DEFAULT 0, status TEXT, details TEXT);''')
    finally:
        conn.close()

def job_status(name):
    init_news()
    conn = get_conn()
    try:
        row = conn.execute('SELECT * FROM background_jobs WHERE name=?', (name,)).fetchone()
        return dict(row) if row else {'name': name, 'status': 'not_run', 'last_success': None}
    finally:
        conn.close()

def news_revision():
    return job_status('news').get('last_success') or 0

def live_rows():
    init_news()
    conn = get_conn()
    try:
        return [json.loads(row['payload']) for row in conn.execute('SELECT payload FROM live_news')]
    finally:
        conn.close()

def acquire_job(name, interval, lease_seconds=900):
    init_news()
    conn = get_conn()
    now = time.time()
    try:
        conn.execute('INSERT OR IGNORE INTO background_jobs(name) VALUES (?)', (name,))
        changed = conn.execute('''UPDATE background_jobs SET lease_until=?,last_started=?,status='running'
            WHERE name=? AND lease_until<? AND (last_started IS NULL OR last_started<?)''',
            (now + lease_seconds, now, name, now, now - interval)).rowcount
        conn.commit()
        return bool(changed)
    finally:
        conn.close()

def finish_job(name, details, success=True):
    conn = get_conn()
    try:
        conn.execute('''UPDATE background_jobs SET lease_until=0,status=?,details=?,
            last_success=CASE WHEN ? THEN ? ELSE last_success END WHERE name=?''',
            ('ok' if success else 'failed', json.dumps(details, ensure_ascii=False), success, time.time(), name))
        conn.commit()
    finally:
        conn.close()

@lru_cache(maxsize=1)
def pipeline():
    root = Path(PROJECT_ROOT)
    with (root / 'configs/keywords.yaml').open(encoding='utf-8') as file:
        keywords = yaml.safe_load(file)
    with (root / 'configs/provinces.yaml').open(encoding='utf-8') as file:
        provinces = yaml.safe_load(file)
    classifier = joblib.load(root / 'data/models/news_risk_tfidf.joblib')
    return keywords, provinces, classifier

def parse_feed(content):
    root = ET.fromstring(content)
    rows = []
    for item in root.findall('./channel/item')[:100]:
        title = html.unescape(item.findtext('title') or '').strip()
        url = item.findtext('link') or ''
        try:
            published = parsedate_to_datetime(item.findtext('pubDate') or '')
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published > datetime.now(timezone.utc):
                continue
        except (ValueError, TypeError):
            continue
        if len(title) < 15 or not url.startswith('https://'):
            continue
        # Same syndicated headline on the same date is one observation.
        key = hashlib.sha256(f'{title.casefold()}|{published.date()}'.encode()).hexdigest()
        rows.append({'id': key, 'title': title, 'text': '', 'url': url,
                     'published_at': published.isoformat(), 'source_name': item.findtext('source') or 'Google News RSS',
                     'content_scope': 'rss_headline', 'fetched_at': datetime.now(timezone.utc).isoformat()})
    return rows

def refresh_news():
    keywords, provinces, classifier = pipeline()
    with open(Path(PROJECT_ROOT) / 'configs/gnews_queries.yaml', encoding='utf-8') as file:
        cfg = yaml.safe_load(file)['gnews']
    collected, failures, successes = {}, [], 0
    for query in cfg['queries'][:max(1, min(30, int(os.getenv('NEWS_QUERY_LIMIT', '6'))))]:
        try:
            url = 'https://news.google.com/rss/search?' + urlencode({'q': query['q'] + ' when:7d', 'hl': 'vi', 'gl': 'VN', 'ceid': 'VN:vi'})
            response = requests.get(url, timeout=15, headers={'User-Agent': 'TravelShield/3.0'})
            response.raise_for_status()
            for row in parse_feed(response.content):
                collected[row['id']] = row
            successes += 1
        except (requests.RequestException, ET.ParseError) as exc:
            failures.append({'query': query['name'], 'error': type(exc).__name__})
    rows = []
    for row in collected.values():
        location = match_province(row['title'], '', provinces)
        if not location['province']:
            continue
        features = build_risk_features(row['title'], '', keywords)
        probability = float(classifier.predict_proba([row['title']])[0, 1])
        rows.append({**row, **features, **location, 'quality_pass': True,
                     'p_risk_any': probability, 'news_model_source': 'tfidf_logreg_headline'})
    conn = get_conn()
    try:
        for row in rows:
            conn.execute('INSERT OR IGNORE INTO live_news(id,payload,fetched_at) VALUES (?,?,?)',
                         (row['id'], json.dumps(row, ensure_ascii=False), row['fetched_at']))
        conn.commit()
    finally:
        conn.close()
    if not successes:
        raise RuntimeError('All RSS feeds failed; previous news retained')
    return {'classified': len(rows), 'feeds_ok': successes, 'feed_failures': failures, 'scope': 'rss_headlines'}

@news_router.get('/status')
def status():
    return {'refresh': job_status('news'), 'articles': len(live_rows()), 'interval_seconds': int(os.getenv('NEWS_REFRESH_SECONDS', '21600')),
            'enabled': os.getenv('BACKGROUND_JOBS_ENABLED', 'true').lower() == 'true', 'content_scope': 'rss_headlines'}
