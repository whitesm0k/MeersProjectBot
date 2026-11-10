"""Shared SQLite review queue. Set MEERS_REVIEWS_DB to absolute site/orders.sqlite3 path."""
import os, sqlite3
from pathlib import Path

def connect():
    path=os.getenv('MEERS_REVIEWS_DB','').strip()
    if not path: return None
    if not Path(path).is_file(): return None
    c=sqlite3.connect(path,timeout=15)
    c.row_factory=sqlite3.Row
    return c

def pending():
    c=connect()
    if c is None: return []
    try: return [dict(r) for r in c.execute("SELECT * FROM reviews WHERE status='pending' ORDER BY created_at LIMIT 30")]
    finally: c.close()

def update(rid,status,**extra):
    c=connect()
    if c is None: return
    try:
        with c:
            c.execute('UPDATE reviews SET status=?, published_message_id=COALESCE(?,published_message_id) WHERE id=?', (status,str(extra['published_message_id']) if extra.get('published_message_id') else None,rid))
    finally: c.close()

def insert(item,name):
    c=connect()
    if c is None:return
    try:
        with c:
            c.execute('INSERT OR IGNORE INTO reviews (id,author_id,author_name,product,rating,text,status,created_at) VALUES (?,?,?,?,?,?,?,?)',(item['id'],str(item['author_id']),str(name)[:80],item['product'],item['rating'],item['text'],item['status'],item['created_at']))
    finally:c.close()
