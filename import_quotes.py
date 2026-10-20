"""Import normalized API/crawler output, not a supplier-specific connector.
Usage: python import_quotes.py path/to/quotes.json
No network calls. An authorized source-specific adapter must produce this file.
"""
import json, math, sys, time
from datetime import datetime
from urllib.parse import urlsplit
from app import db, init

def validate(rows):
    if not isinstance(rows,list) or len(rows)>5000:raise ValueError('Expected at most 5000 quote rows')
    checked=[];seen=set()
    for r in rows:
        for k in ('product','name','spec','model','store','store_name','store_address','source_url','source_type','match_key'):
            if not isinstance(r.get(k),str) or not r[k].strip():raise ValueError('Missing '+k)
        u=urlsplit(r['source_url'])
        if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('Source must be a public HTTPS product URL')
        if r['source_type'] not in ('api','webpage'):raise ValueError('source_type must be api or webpage')
        if r.get('currency')!='USD' or r.get('price_basis')!='public':raise ValueError('Only public USD prices supported')
        if r.get('store_verified') is not True:raise ValueError('Store context must be independently verified')
        if type(r.get('pack_quantity')) is not int or r['pack_quantity']<1:raise ValueError('Invalid package quantity')
        if isinstance(r.get('price'),bool) or not isinstance(r.get('price'),(int,float)) or not math.isfinite(r['price']) or r['price']<=0:raise ValueError('Invalid price')
        if r.get('stock') is not None and (type(r['stock']) is not int or r['stock']<0):raise ValueError('stock must be nonnegative integer or null')
        dt=datetime.fromisoformat(r['observed_at'].replace('Z','+00:00'))
        if dt.tzinfo is None or dt.timestamp()>time.time()+300:raise ValueError('Invalid observation timestamp')
        r=dict(r,observed=dt.timestamp());key=(r['product'],r['store'])
        if key in seen:raise ValueError('Duplicate product/store')
        seen.add(key);checked.append(r)
    # One product ID must always mean the same verified model/package/identity.
    identities={}
    for r in checked:
        identity=(r['match_key'],r['model'],r['pack_quantity'],r['spec'])
        if r['product'] in identities and identities[r['product']]!=identity:raise ValueError('Conflicting product identity')
        identities[r['product']]=identity
    return checked

def import_rows(rows):
    checked=validate(rows);init()
    with db() as c:
        existing=[json.loads(r[0]) for r in c.execute('SELECT payload FROM verified_quotes')]
        for r in checked:
            for e in existing:
                if e['product']==r['product'] and any(e[k]!=r[k] for k in ('match_key','model','pack_quantity','spec')):raise ValueError('Identity conflicts with existing product')
                if e['product']==r['product'] and e['store']==r['store'] and e['observed']>r['observed']:raise ValueError('Cannot replace with older observation')
            c.execute('INSERT INTO verified_quotes(product,store,payload,observed) VALUES(?,?,?,?) ON CONFLICT(product,store) DO UPDATE SET payload=excluded.payload, observed=excluded.observed',(r['product'],r['store'],json.dumps(r),r['observed']))
    return len(checked)
if __name__=='__main__':
    try:print('Imported',import_rows(json.load(open(sys.argv[1],encoding='utf-8'))),'validated quotes')
    except (ValueError,KeyError,TypeError) as e:raise SystemExit('Import rejected: '+str(e))
