"""입력값 없는 causal structural hashing. 사전 학습 vocabulary와 UNK를 사용하지 않습니다."""
import hashlib
import re
from urllib.parse import urlsplit, unquote
import numpy as np
from .data import time_of

UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
VOLATILE = re.compile(r'\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+Z-]+)?|\b[0-9a-f]{16,}\b|\d+', re.I)

def normalize(text):
    text = unquote(str(text or '')).lower()
    text = UUID.sub(':id', text)
    return VOLATILE.sub(':id', text)

def normalized_path(text):
    return normalize(urlsplit(str(text or '')).path)

def semantic_text(event, config):
    # Free-form target text, payload and input values are never retained.
    title = event.get('page_title', '')
    return title if title in config.get('safe_page_titles', []) else '<redacted-title>'

def target_role(e):
    selector = e.get('target_selector', '').lower()
    if any(x in selector for x in ('sidebar', 'nav', 'menu')):
        return 'navigation'
    if e.get('element_tag') in ('input','textarea','select'):
        return 'input_control'
    if any(x in selector for x in ('modal', 'dialog', 'popup')):
        return 'dialog_control'
    if e.get('element_tag') in ('li','td'):
        return 'item'
    return e.get('element_tag','') or 'unknown'

def structure(e, config):
    status = e.get('api_status_code', '')
    return {'event': e.get('event_type',''), 'action': e.get('interaction_type',''),
            'tag': e.get('element_tag',''), 'method': e.get('api_method','').upper(),
            'status': status[:1]+'xx' if status.isdigit() else 'none',
            'page': normalized_path(e.get('page_url','')),
            'api': normalized_path(e.get('api_path','')),
            'title': semantic_text(e, config), 'role': target_role(e)}

def hash_tokens(tokens, dimension):
    result = np.zeros(dimension, dtype=np.float32)
    for token in tokens:
        d = hashlib.sha256(token.encode('utf-8')).digest()
        result[int.from_bytes(d[:8], 'big') % dimension] += 1 if d[8] & 1 else -1
    norm = np.linalg.norm(result)
    return result / max(norm, 1e-8)

def event_vector(e, config, dimension=None):
    s = structure(e, config)
    tokens = [k+'='+v for k,v in s.items()]
    for field in ('page','api','title'):
        value = '^'+s[field]+'$'
        for n in range(config['ngram_min'], config['ngram_max']+1):
            tokens.extend(field+':'+value[i:i+n] for i in range(max(0,len(value)-n+1)))
    return hash_tokens(tokens, dimension or config['hash_dim'])

def features(stream, config):
    """Only present/past events; no manifest positions or future context."""
    vectors = []
    times = [time_of(e) for e in stream]
    for i,e in enumerate(stream):
        s = structure(e,config)
        prev = structure(stream[i-1],config) if i else None
        gap = max(0,times[i]-times[i-1]) if i else 0
        density = sum(times[i]-t<=config['density_window_seconds'] for t in times[:i+1])
        temporal = np.array([
            min(np.log1p(gap)/8,1), min(np.log1p(times[i]-times[0])/10,1),
            min(density/20,1), float(gap>=config['inactivity_seconds']),
            float(prev is not None and s['page']!=prev['page']),
            float(s['role']=='navigation'), float('popup' in s['action']),
            float(s['action']=='submit'), float(s['method'] in ('POST','PUT','PATCH','DELETE')),
            float(s['status']=='2xx'), float(prev is not None and prev['action']=='popup_close'),
            float(prev is not None and prev['method'] in ('POST','PUT','PATCH','DELETE') and prev['status']=='2xx')], dtype=np.float32)
        previous = event_vector(stream[i-1],config,config['previous_hash_dim']) if i else np.zeros(config['previous_hash_dim'],np.float32)
        vectors.append(np.concatenate([event_vector(e,config), previous,temporal]))
    return np.asarray(vectors,dtype=np.float32)

def rule_boundaries(stream, config):
    result=[]
    for i,e in enumerate(stream):
        if not i:
            result.append(False);continue
        prev=stream[i-1]; s=structure(e,config); p=structure(prev,config)
        menu=s['action']=='click' and s['role']=='navigation'
        route=s['action'] in ('route_change','page_view') and s['page']!=p['page'] and p['role']!='navigation'
        restart=s['action']=='click' and (p['action']=='popup_close' or (p['method'] in ('POST','PATCH','PUT') and p['status']=='2xx'))
        result.append(menu or route or restart or time_of(e)-time_of(prev)>=config['inactivity_seconds'])
    return np.asarray(result, dtype=bool)
