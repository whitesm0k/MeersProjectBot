"""HTTP bridge between Bothost and Railway, with optional legacy shared SQLite."""
import os
import json
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path

def _api(path, payload=None):
    base = os.getenv('MEERS_SITE_URL', '').rstrip('/')
    token = os.getenv('REVIEW_BRIDGE_TOKEN', '')
    if not base or not token:
        return None
    headers = {'X-Review-Bridge-Token': token, 'Accept': 'application/json'}
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(base + path, data=body, headers=headers,
                                 method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)

def connect():
    path = os.getenv('MEERS_REVIEWS_DB', '').strip()
    if not path or not Path(path).is_file():
        return None
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    return c

def pending():
    if os.getenv('MEERS_SITE_URL') and os.getenv('REVIEW_BRIDGE_TOKEN'):
        return _api('/api/bridge/reviews/pending')['reviews']
    c = connect()
    if c is None:
        return []
    try:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reviews WHERE status='pending' ORDER BY created_at LIMIT 30")]
    finally:
        c.close()

def update(rid, status, **extra):
    if os.getenv('MEERS_SITE_URL') and os.getenv('REVIEW_BRIDGE_TOKEN'):
        return _api('/api/bridge/reviews/' + urllib.parse.quote(str(rid), safe='') + '/status',
                    {'status': status, 'published_message_id': extra.get('published_message_id')})
    c = connect()
    if c is None:
        return
    try:
        with c:
            c.execute('UPDATE reviews SET status=?, published_message_id=COALESCE(?,published_message_id) WHERE id=?',
                      (status, str(extra['published_message_id']) if extra.get('published_message_id') else None, rid))
    finally:
        c.close()

def insert(item, name):
    # Bot-created reviews are stored in the bot's JSON state. Only website reviews
    # need remote synchronization. Keep legacy local SQLite support.
    c = connect()
    if c is None:
        return
    try:
        with c:
            c.execute('INSERT OR IGNORE INTO reviews (id,author_id,author_name,product,rating,text,status,created_at) VALUES (?,?,?,?,?,?,?,?)',
                      (item['id'], str(item['author_id']), str(name)[:80], item['product'],
                       item['rating'], item['text'], item['status'], item['created_at']))
    finally:
        c.close()
