"""V6.2 notebook에서 검토 후 추출한 forward/전처리 함수. 학습 루프는 포함하지 않습니다.
Source SHA-256: c53cc08dcab8ec5ddf758198422ecc5e3a1d5dbdda08b2d65a111af0fba7acf4
"""
import math
from collections import Counter
from urllib.parse import urlparse
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import Dataset
from sklearn.mixture import GaussianMixture
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score

SEED = 42
MODEL_VERSION = 'v6.2'
USE_SEMANTIC_ENCODER = True
SEMANTIC_MODEL_NAME = 'intfloat/multilingual-e5-small'
SEMANTIC_BATCH_SIZE = 128
SEMANTIC_FALLBACK_DIM = 384
SEMANTIC_CACHE = True
SEMANTIC_WEIGHT = 0.2
SEMANTIC_WEIGHT_CANDIDATES = [0.0, 0.1, 0.2, 0.3, 0.5, 1.0]
ENABLE_GOLD_EVAL = True
GOLD_EVAL_DATASET = 'poc_full'
USE_STRUCTURAL_BOUNDARY = True
STRUCT_DIM = 48
STRUCT_TARGET_WEIGHT = 0.35
STRUCT_BOUNDARY_SPARSITY_WEIGHT = 0.01
STRUCTURAL_FIELDS = ['struct_api_family', 'struct_page_path', 'struct_page_title']
USE_TRANSITION_CONTRASTIVE_WORKFLOW_BOUNDARY = True
WORKFLOW_TRANSITION_EPOCHS = 8
WORKFLOW_TRANSITION_BATCH_SIZE = 256
WORKFLOW_TRANSITION_LR = 0.0003
WORKFLOW_TRANSITION_TEMPERATURE = 0.1
WORKFLOW_TRANSITION_BLEND_WEIGHT = 0.45
THRESHOLD_MODE = 'calibrated_gmm'
THRESHOLD_POSTERIOR_MIN = 0.8
THRESHOLD_BIC_GAIN_MIN = 10.0
THRESHOLD_MIN_SEPARATION_SIGMA = 1.0
THRESHOLD_ROBUST_Z_FALLBACK = 2.5
EVAL_V2_PRIMARY_MODE = 'context_ge1'
EVAL_V2_PERSISTENT_MIN_HITS = 2
EVAL_V2_PERSISTENT_MIN_DWELL_SEC = 3.0
ENABLE_PROTOTYPE_STABILITY_EVAL = True
PROTOTYPE_STABILITY_SEEDS = [41, 42, 43]
USE_CONSENSUS_PROTOTYPES = True
PROTOTYPE_ENSEMBLE_SEEDS = [41, 42, 43, 44, 45]
PROTOTYPE_OPT_STEPS = 300
PROTOTYPE_LOG_EVERY = 50
PROTOTYPE_EARLY_STOP_PATIENCE = 80
PROTOTYPE_MIN_DELTA = 1e-05
SEGMENT_CONSENSUS_K_MIN = 10
SEGMENT_CONSENSUS_K_MAX = 18
WORKFLOW_CONSENSUS_K_MIN = 7
WORKFLOW_CONSENSUS_K_MAX = 12
REPORT_TARGET_MIN_WORKFLOWS = 7
REPORT_MAX_WORKFLOWS = 10
REPORT_MIN_INSTANCE_SUPPORT = 5
REPORT_SCORE_THRESHOLD = 0.55
USE_SALIENCE_GATE = False
USE_VICREG = False
FAST_DEV_RUN = False
FULL_DATA_RUN = True
DATASET_NAME = 'poc_full'
FULL_DATA_SUBDIR_CANDIDATES = ['poc_full', 'full', '', 'urangi']
USE_USER_TRAJECTORY = True
SESSION_USER_ID_COLUMN = 'user_id'
SESSION_KEY_CANDIDATES = ['session_id', 'id']
USER_TRAJECTORY_GAP_MINUTES = 180
USER_TRAJECTORY_BREAK_ON_DATE_CHANGE = True
USER_TRAJECTORY_MAX_WINDOW_INSTANCES = 12
USER_TRAJECTORY_MAX_WINDOW_MINUTES = 240
USER_TRAJECTORY_SUPPORT_SCORE = 0.4
EVENT_WINDOW = 128
EVENT_STRIDE = 64
MAX_TEXT_BYTES = 192
MASK_PROB = 0.15
D_MODEL = 128
NHEAD = 4
EVENT_LAYERS = 3
FF = 256
DROPOUT = 0.1
BATCH_SIZE = 16
EVENT_EPOCHS = 12
BOUNDARY_EPOCHS = 6
SEGMENT_WINDOW = 32
SEGMENT_STRIDE = 16
SEGMENT_EPOCHS = 8
WORKFLOW_BOUNDARY_EPOCHS = 6
MIN_SEGMENT_EVENTS = 3
MIN_WORKFLOW_SEGMENTS = 2
PROTOTYPE_EPOCHS = 20
PROTOTYPE_LR = 0.001
MAX_SEGMENT_PROTOTYPES = 32
MAX_WORKFLOW_PROTOTYPES = 16
KEEP_MODEL_BUNDLE = True
PREVIEW_MAX_MODELS = 12
PREVIEW_INSTANCES_PER_MODEL = 20
PREVIEW_MAX_INPUTS_PER_INSTANCE = 120
IN_COLAB = False
BASE_DIR = None
RESET_OUTPUT_DIR = True
device = torch.device('cpu')
cat_cols = ['event_type','interaction_type','element_tag','api_method']
struct_cols = STRUCTURAL_FIELDS
event_threshold_rows = []


def safe_str(x):
    if x is None:
        return ''
    try:
        if pd.isna(x):
            return ''
    except Exception:
        pass
    s = str(x).strip()
    return '' if s.lower() in {'nan', 'none', 'null', 'nat', '[null]'} else s

def url_path(x):
    s = safe_str(x)
    if not s:
        return ''
    try:
        p = urlparse(s)
        return p.path or s.split('?')[0]
    except Exception:
        return s.split('?')[0]

def structural_api_family(x):
    p = url_path(x)
    if not p:
        return ''
    parts = [z for z in p.split('/') if z]
    if len(parts) <= 1:
        return p
    return '/' + '/'.join(parts[:-1])

def structural_page_path(x):
    return url_path(x)

def structural_title(x):
    return safe_str(x)

def derive_worker_id(row):
    for col in ['actor_key', 'login_id', 'user_id', 'worker_id', 'employee_id']:
        if col in row.index:
            v = safe_str(row.get(col))
            if v:
                return v
    wk = safe_str(row.get('workflow_key'))
    if wk:
        return wk.split('#W')[0]
    sid = safe_str(row.get('session_id'))
    if sid:
        return f'session:{sid}'
    return 'worker_0'

def build_event_text(row):
    """
    V4.2 Byte CNN 입력.
    technical string + UI text를 모두 유지한다.
    """
    fields = [('EVT', row.get('event_type')), ('INT', row.get('interaction_type')), ('TAG', row.get('element_tag')), ('TEXT', row.get('element_text')), ('LABEL', row.get('associated_label')), ('API', row.get('api_path')), ('PAGE', row.get('page_title')), ('PATH', url_path(row.get('page_url'))), ('TESTID', row.get('data_testid'))]
    parts = []
    for (k, v) in fields:
        s = safe_str(v)
        if s:
            parts.append(f'[{k}] {s}')
    return ' '.join(parts)[:1200]

def build_semantic_text(row):
    """
    V5.2의 유일한 representation 추가.

    Byte CNN은 API/path/technical string을 그대로 처리하고,
    semantic encoder는 사람이 읽는 UI 의미만 보강한다.
    """
    fields = [('PAGE', row.get('page_title')), ('LABEL', row.get('associated_label')), ('TEXT', row.get('element_text'))]
    parts = []
    for (k, v) in fields:
        s = safe_str(v)
        if s:
            parts.append(f'{k}: {s}')
    return ' | '.join(parts)[:700]

def byte_encode(text, max_len):
    b = safe_str(text).encode('utf-8', errors='ignore')[:max_len]
    arr = np.zeros(max_len, dtype=np.int64)
    if b:
        arr[:len(b)] = np.frombuffer(b, dtype=np.uint8).astype(np.int64) + 1
    return arr

def prep(df):
    df = df.copy()
    df['event_time_parsed'] = pd.to_datetime(df['event_time'], errors='coerce')
    sort_cols = ['event_time_parsed']
    if 'id' in df.columns:
        sort_cols.append('id')
    df = df.sort_values(sort_cols, kind='stable').reset_index(drop=True)
    df['global_event_idx'] = np.arange(len(df))
    df['stream_id'] = df.apply(derive_worker_id, axis=1)
    df['event_text'] = df.apply(build_event_text, axis=1)
    df['semantic_text'] = df.apply(build_semantic_text, axis=1)
    df['struct_api_family'] = df['api_path'].map(structural_api_family) if 'api_path' in df.columns else ''
    df['struct_page_path'] = df['page_url'].map(structural_page_path) if 'page_url' in df.columns else ''
    df['struct_page_title'] = df['page_title'].map(structural_title) if 'page_title' in df.columns else ''
    df['delta_sec'] = df.groupby('stream_id')['event_time_parsed'].diff().dt.total_seconds().clip(lower=0).fillna(0)
    for c in ['step_duration_ms', 'api_latency_ms', 'api_status_code']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        else:
            df[c] = 0.0
    return df

def raw_num(frame):
    x = np.stack([np.log1p(frame['delta_sec'].values), np.log1p(frame['step_duration_ms'].values), np.log1p(frame['api_latency_ms'].values), frame['api_status_code'].values / 600.0], axis=1).astype('float32')
    return x

def make_windows(frame, window, stride):
    out = []
    for (sid, g) in frame.groupby('stream_id', sort=False):
        ids = g.sort_values('event_time_parsed')['global_event_idx'].to_numpy()
        if len(ids) == 0:
            continue
        if len(ids) <= window:
            out.append((sid, ids))
        else:
            starts = list(range(0, len(ids) - window + 1, stride))
            if starts[-1] != len(ids) - window:
                starts.append(len(ids) - window)
            for st in starts:
                out.append((sid, ids[st:st + window]))
    return out

class EventWindowDataset(Dataset):

    def __init__(self, windows, arrays, mask_prob=0.0):
        self.windows = windows
        self.a = arrays
        self.mask_prob = mask_prob

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, i):
        (sid, ids) = self.windows[i]
        L = len(ids)
        mask = np.zeros(L, dtype=bool)
        if self.mask_prob > 0 and L > 1:
            mask = np.random.rand(L) < self.mask_prob
            if not mask.any():
                mask[np.random.randint(0, L)] = True
        return {'stream_id': sid, 'global_idx': torch.tensor(ids, dtype=torch.long), 'bytes': torch.tensor(self.a['bytes'][ids], dtype=torch.long), 'semantic': torch.tensor(self.a['semantic'][ids], dtype=torch.float32), **{c: torch.tensor(self.a[c][ids], dtype=torch.long) for c in cat_cols}, **{c: torch.tensor(self.a[c][ids], dtype=torch.long) for c in struct_cols}, 'num': torch.tensor(self.a['num'][ids], dtype=torch.float32), 'mask_pos': torch.tensor(mask, dtype=torch.bool), 'length': L}

def collate(batch):
    B = len(batch)
    L = max((x['length'] for x in batch))
    T = batch[0]['bytes'].shape[1]
    S = batch[0]['semantic'].shape[1]
    out = {'stream_id': [x['stream_id'] for x in batch], 'lengths': torch.tensor([x['length'] for x in batch], dtype=torch.long)}
    out['global_idx'] = torch.full((B, L), -1, dtype=torch.long)
    out['bytes'] = torch.zeros((B, L, T), dtype=torch.long)
    out['semantic'] = torch.zeros((B, L, S), dtype=torch.float32)
    out['num'] = torch.zeros((B, L, 4), dtype=torch.float32)
    out['mask_pos'] = torch.zeros((B, L), dtype=torch.bool)
    out['attention_mask'] = torch.zeros((B, L), dtype=torch.bool)
    for c in cat_cols:
        out[c] = torch.zeros((B, L), dtype=torch.long)
    for c in struct_cols:
        out[c] = torch.zeros((B, L), dtype=torch.long)
    for (i, x) in enumerate(batch):
        n = x['length']
        out['global_idx'][i, :n] = x['global_idx']
        out['bytes'][i, :n] = x['bytes']
        out['semantic'][i, :n] = x['semantic']
        out['num'][i, :n] = x['num']
        out['mask_pos'][i, :n] = x['mask_pos']
        out['attention_mask'][i, :n] = True
        for c in cat_cols:
            out[c][i, :n] = x[c]
        for c in struct_cols:
            out[c][i, :n] = x[c]
    return out

def todev(batch):
    return {k: v.to(device) if torch.is_tensor(v) else v for (k, v) in batch.items()}

class ByteCNN(nn.Module):

    def __init__(self, d_model):
        super().__init__()
        self.emb = nn.Embedding(257, 32, padding_idx=0)
        self.conv = nn.Sequential(nn.Conv1d(32, 64, 3, padding=1), nn.GELU(), nn.Conv1d(64, d_model, 5, padding=2), nn.GELU())

    def forward(self, x):
        (B, L, T) = x.shape
        y = self.emb(x.reshape(B * L, T)).transpose(1, 2)
        y = self.conv(y)
        mask = x.reshape(B * L, T).ne(0).unsqueeze(1)
        y = y.masked_fill(~mask, -10000.0).amax(-1)
        empty = ~mask.any(-1).squeeze(1)
        y = torch.where(empty.unsqueeze(-1), torch.zeros_like(y), y)
        return y.reshape(B, L, -1)

class EventTransformer(nn.Module):
    """
    V5.2 구조를 유지하되 semantic embedding 영향력을 축소한다.

    기존 V4.2:
        byte + numeric + categorical

    V5.3:
        byte + SEMANTIC_WEIGHT × semantic + numeric + categorical

    이후 Transformer / SSL heads 구조는 V4.2와 동일.
    """

    def __init__(self, vocabs, semantic_dim):
        super().__init__()
        self.text = ByteCNN(D_MODEL)
        self.semantic = nn.Sequential(nn.LayerNorm(semantic_dim), nn.Linear(semantic_dim, D_MODEL, bias=False))
        self.cat = nn.ModuleDict({c: nn.Embedding(len(vocabs[c]), D_MODEL, padding_idx=0) for c in cat_cols})
        self.num = nn.Sequential(nn.Linear(4, D_MODEL), nn.GELU(), nn.Linear(D_MODEL, D_MODEL))
        self.pos = nn.Embedding(EVENT_WINDOW, D_MODEL)
        self.mask_token = nn.Parameter(torch.randn(D_MODEL) * 0.02)
        layer = nn.TransformerEncoderLayer(D_MODEL, NHEAD, FF, DROPOUT, batch_first=True, norm_first=True)
        self.tr = nn.TransformerEncoder(layer, EVENT_LAYERS)
        self.norm = nn.LayerNorm(D_MODEL)
        self.mask_event = nn.Linear(D_MODEL, len(vocabs['event_type']))
        self.mask_int = nn.Linear(D_MODEL, len(vocabs['interaction_type']))
        self.next_event = nn.Linear(D_MODEL, len(vocabs['event_type']))
        self.next_int = nn.Linear(D_MODEL, len(vocabs['interaction_type']))

    def forward(self, b, mask_events=True):
        x = self.text(b['bytes']) + SEMANTIC_WEIGHT * self.semantic(b['semantic']) + self.num(b['num'])
        for c in cat_cols:
            x = x + self.cat[c](b[c])
        if mask_events:
            x = torch.where(b['mask_pos'].unsqueeze(-1), self.mask_token.view(1, 1, -1), x)
        L = x.shape[1]
        x = x + self.pos(torch.arange(L, device=x.device)).view(1, L, -1)
        h = self.norm(self.tr(x, src_key_padding_mask=~b['attention_mask']))
        return h

    def pooled(self, h, m):
        return (h * m.unsqueeze(-1)).sum(1) / m.sum(1, keepdim=True).clamp_min(1)

class StructuralIdentityEncoder(nn.Module):

    def __init__(self, struct_vocabs, d_struct=STRUCT_DIM):
        super().__init__()
        self.emb = nn.ModuleDict({c: nn.Embedding(len(struct_vocabs[c]), d_struct, padding_idx=0) for c in struct_cols})
        self.norm = nn.LayerNorm(d_struct)

    def forward(self, b):
        vecs = []
        masks = []
        for c in struct_cols:
            ids = b[c]
            vecs.append(self.emb[c](ids))
            masks.append(ids.ne(0).float())
        stacked = torch.stack(vecs, dim=-2)
        present = torch.stack(masks, dim=-1)
        denom = present.sum(-1, keepdim=True).clamp_min(1.0)
        pooled = (stacked * present.unsqueeze(-1)).sum(-2) / denom
        pooled = self.norm(pooled)
        any_present = present.sum(-1).gt(0)
        return torch.where(any_present.unsqueeze(-1), pooled, torch.zeros_like(pooled))

class NeuralBoundary(nn.Module):

    def __init__(self, d, struct_vocabs):
        super().__init__()
        self.context_conv = nn.Sequential(nn.Conv1d(d, d, 3, padding=1), nn.GELU(), nn.Conv1d(d, d, 3, padding=1), nn.GELU())
        self.struct_encoder = StructuralIdentityEncoder(struct_vocabs, STRUCT_DIM)
        self.struct_conv = nn.Sequential(nn.Conv1d(STRUCT_DIM, STRUCT_DIM, 3, padding=1), nn.GELU(), nn.Conv1d(STRUCT_DIM, STRUCT_DIM, 3, padding=1), nn.GELU())
        feat_dim = d * 3 + STRUCT_DIM * 3 + len(struct_cols)
        self.mlp = nn.Sequential(nn.Linear(feat_dim, d), nn.GELU(), nn.Dropout(DROPOUT), nn.Linear(d, 1))

    @staticmethod
    def raw_structural_change_features(b):
        changes = []
        for c in struct_cols:
            left = b[c][:, :-1]
            right = b[c][:, 1:]
            available = left.ne(0) | right.ne(0)
            changes.append((left.ne(right) & available).float())
        return torch.stack(changes, dim=-1)

    @staticmethod
    def structural_change_score(b):
        feat = NeuralBoundary.raw_structural_change_features(b)
        available = []
        for c in struct_cols:
            left = b[c][:, :-1]
            right = b[c][:, 1:]
            available.append((left.ne(0) | right.ne(0)).float())
        avail = torch.stack(available, dim=-1)
        return feat.sum(-1) / avail.sum(-1).clamp_min(1.0)

    def forward(self, h, b):
        c = self.context_conv(h.transpose(1, 2)).transpose(1, 2)
        s = self.struct_encoder(b)
        s = self.struct_conv(s.transpose(1, 2)).transpose(1, 2)
        (a, bb) = (c[:, :-1], c[:, 1:])
        (sa, sb) = (s[:, :-1], s[:, 1:])
        raw = self.raw_structural_change_features(b)
        feat = torch.cat([a, bb, torch.abs(a - bb), sa, sb, torch.abs(sa - sb), raw], -1)
        return self.mlp(feat).squeeze(-1)

def threshold_gmm_legacy(vals):
    """
    V5.3~V5.6 비교용 기존 threshold.
    최종 segmentation에는 사용하지 않는다.
    """
    vals = np.asarray(vals, float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < 8 or np.std(vals) < 1e-06:
        return float(np.median(vals) + np.std(vals)) if len(vals) else 0.5
    try:
        gm = GaussianMixture(2, random_state=SEED).fit(vals.reshape(-1, 1))
        means = np.sort(gm.means_.ravel())
        return float(means.mean())
    except Exception:
        return float(np.quantile(vals, 0.85))

def _robust_center_scale(vals):
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return (0.0, 1.0)
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    scale = max(1.4826 * mad, float(np.std(vals)) * 0.25, 1e-06)
    return (med, scale)

def threshold_calibrated(vals, return_meta=False):
    """
    1-component vs 2-component GMM을 비교하고,
    충분히 분리된 boundary component가 있을 때만
    high-component posterior를 cut 근거로 사용한다.

    분리 구조가 약하면 median-relative quantile이 아니라
    robust absolute upper-tail threshold로 fallback한다.
    """
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    meta = {'n': int(len(vals)), 'mode': 'empty', 'threshold': 0.5, 'legacy_threshold': None, 'bic_1': None, 'bic_2': None, 'bic_gain': None, 'low_mean': None, 'high_mean': None, 'separation_sigma': None, 'posterior_min': float(THRESHOLD_POSTERIOR_MIN)}
    if len(vals) == 0:
        return (0.5, meta) if return_meta else 0.5
    legacy = threshold_gmm_legacy(vals)
    meta['legacy_threshold'] = float(legacy)
    (med, scale) = _robust_center_scale(vals)
    robust_threshold = float(med + THRESHOLD_ROBUST_Z_FALLBACK * scale)
    if len(vals) < 8 or np.std(vals) < 1e-06:
        threshold = robust_threshold
        meta.update({'mode': 'robust_tail_small_n', 'threshold': float(threshold)})
        return (threshold, meta) if return_meta else threshold
    try:
        gm1 = GaussianMixture(1, random_state=SEED).fit(vals.reshape(-1, 1))
        gm2 = GaussianMixture(2, random_state=SEED).fit(vals.reshape(-1, 1))
        bic1 = float(gm1.bic(vals.reshape(-1, 1)))
        bic2 = float(gm2.bic(vals.reshape(-1, 1)))
        bic_gain = bic1 - bic2
        means = gm2.means_.ravel()
        order = np.argsort(means)
        low_idx = int(order[0])
        high_idx = int(order[1])
        low_mean = float(means[low_idx])
        high_mean = float(means[high_idx])
        cov = np.asarray(gm2.covariances_).reshape(-1)
        pooled_sd = math.sqrt(max((float(cov[low_idx]) + float(cov[high_idx])) / 2.0, 1e-08))
        separation_sigma = abs(high_mean - low_mean) / pooled_sd
        meta.update({'bic_1': bic1, 'bic_2': bic2, 'bic_gain': float(bic_gain), 'low_mean': low_mean, 'high_mean': high_mean, 'separation_sigma': float(separation_sigma)})
        if bic_gain >= THRESHOLD_BIC_GAIN_MIN and separation_sigma >= THRESHOLD_MIN_SEPARATION_SIGMA:
            posterior = gm2.predict_proba(vals.reshape(-1, 1))[:, high_idx]
            accepted = vals[posterior >= THRESHOLD_POSTERIOR_MIN]
            if len(accepted):
                threshold = float(np.min(accepted))
                meta['mode'] = 'gmm_high_posterior'
            else:
                threshold = robust_threshold
                meta['mode'] = 'robust_tail_no_posterior'
        else:
            threshold = robust_threshold
            meta['mode'] = 'robust_tail_weak_mixture'
    except Exception as e:
        threshold = robust_threshold
        meta['mode'] = 'robust_tail_exception'
        meta['exception'] = safe_str(e)
    meta['threshold'] = float(threshold)
    return (threshold, meta) if return_meta else threshold

def make_segments(df, emb, probs):
    segrows = []
    members = []
    sid_counter = 0
    for (stream, g) in df.groupby('stream_id', sort=False):
        g = g.sort_values('event_time_parsed')
        ids = g.global_event_idx.to_numpy()
        vals = probs[ids][1:] if len(ids) > 1 else np.asarray([])
        (th, meta) = threshold_calibrated(vals, return_meta=True)
        legacy_th = threshold_gmm_legacy(vals) if len(vals) else 1.0
        raw_starts = [0] + [i for i in range(1, len(ids)) if probs[ids[i]] >= th]
        legacy_starts = [0] + [i for i in range(1, len(ids)) if probs[ids[i]] >= legacy_th]
        filt = [0]
        for s in raw_starts[1:]:
            if s - filt[-1] >= MIN_SEGMENT_EVENTS:
                filt.append(s)
        if len(ids) - filt[-1] < MIN_SEGMENT_EVENTS and len(filt) > 1:
            filt.pop()
        legacy_filt = [0]
        for s in legacy_starts[1:]:
            if s - legacy_filt[-1] >= MIN_SEGMENT_EVENTS:
                legacy_filt.append(s)
        if len(ids) - legacy_filt[-1] < MIN_SEGMENT_EVENTS and len(legacy_filt) > 1:
            legacy_filt.pop()
        event_threshold_rows.append({'stream_id': safe_str(stream), 'event_count': int(len(ids)), 'legacy_threshold': float(legacy_th), 'calibrated_threshold': float(th), 'legacy_segment_count': int(len(legacy_filt)), 'calibrated_segment_count': int(len(filt)), **meta})
        for (j, s) in enumerate(filt):
            e = filt[j + 1] - 1 if j + 1 < len(filt) else len(ids) - 1
            mids = ids[s:e + 1]
            sid_counter += 1
            txt = g.iloc[s:e + 1]
            evidence = []
            for col in ['element_text', 'associated_label', 'api_path', 'interaction_type']:
                for v in txt[col].tolist() if col in txt else []:
                    v = safe_str(v)
                    if v and v not in evidence:
                        evidence.append(v)
                    if len(evidence) >= 8:
                        break
                if len(evidence) >= 8:
                    break
            segrows.append({'segment_idx': sid_counter - 1, 'segment_id': f'S{sid_counter:05d}', 'stream_id': stream, 'start_global_idx': int(mids[0]), 'end_global_idx': int(mids[-1]), 'event_count': len(mids), 'start_time': txt.event_time_parsed.iloc[0], 'end_time': txt.event_time_parsed.iloc[-1], 'boundary_threshold': th, 'boundary_prob_start': 1.0 if s == 0 else float(probs[mids[0]]), 'evidence': ' | '.join(evidence)})
            members.append(mids)
    return (pd.DataFrame(segrows), members)

class SegmentSeqDataset(Dataset):

    def __init__(self, segdf, vectors, window, stride, mask_prob=0.15):
        self.v = vectors
        self.items = []
        self.mask_prob = mask_prob
        for (sid, g) in segdf.groupby('stream_id', sort=False):
            idx = g.sort_values('start_global_idx').segment_idx.to_numpy()
            if len(idx) <= window:
                self.items.append((sid, idx))
            else:
                starts = list(range(0, len(idx) - window + 1, stride))
                if starts[-1] != len(idx) - window:
                    starts.append(len(idx) - window)
                for st in starts:
                    self.items.append((sid, idx[st:st + window]))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        (sid, ids) = self.items[i]
        L = len(ids)
        mask = np.random.rand(L) < self.mask_prob if self.mask_prob else np.zeros(L, bool)
        if self.mask_prob and L > 1 and (not mask.any()):
            mask[np.random.randint(L)] = True
        return {'stream_id': sid, 'segment_idx': torch.tensor(ids, dtype=torch.long), 'vectors': torch.tensor(self.v[ids], dtype=torch.float32), 'mask_pos': torch.tensor(mask, dtype=torch.bool), 'length': L}

def seg_collate(batch):
    B = len(batch)
    L = max((x['length'] for x in batch))
    D = batch[0]['vectors'].shape[-1]
    out = {'stream_id': [x['stream_id'] for x in batch], 'lengths': torch.tensor([x['length'] for x in batch], dtype=torch.long), 'segment_idx': torch.full((B, L), -1, dtype=torch.long), 'vectors': torch.zeros(B, L, D, dtype=torch.float32), 'mask_pos': torch.zeros(B, L, dtype=torch.bool), 'attention_mask': torch.zeros(B, L, dtype=torch.bool)}
    for (i, x) in enumerate(batch):
        n = x['length']
        out['segment_idx'][i, :n] = x['segment_idx']
        out['vectors'][i, :n] = x['vectors']
        out['mask_pos'][i, :n] = x['mask_pos']
        out['attention_mask'][i, :n] = True
    return out

class SegmentTransformer(nn.Module):

    def __init__(self, d):
        super().__init__()
        self.inp = nn.Linear(d, d)
        self.mask = nn.Parameter(torch.randn(d) * 0.02)
        self.pos = nn.Embedding(SEGMENT_WINDOW, d)
        layer = nn.TransformerEncoderLayer(d_model=d, nhead=NHEAD, dim_feedforward=FF, dropout=DROPOUT, batch_first=True, norm_first=True)
        self.tr = nn.TransformerEncoder(layer, num_layers=2)
        self.norm = nn.LayerNorm(d)
        self.recon = nn.Linear(d, d)
        self.next = nn.Linear(d, d)

    def forward(self, b, mask=True):
        x = self.inp(b['vectors'])
        if mask:
            x = torch.where(b['mask_pos'].unsqueeze(-1), self.mask.view(1, 1, -1), x)
        L = x.size(1)
        pos = torch.arange(L, device=x.device)
        x = x + self.pos(pos)
        x = self.tr(x, src_key_padding_mask=~b['attention_mask'])
        return self.norm(x)

class WorkflowBoundary(nn.Module):
    """
        Workflow-level boundary detector.

        V5.4 structural identity is intentionally applied ONLY to the event boundary.
        At this level the inputs are latent segment embeddings, so we keep the
        original V5.3/V4.2 contextual boundary architecture unchanged.
        """

    def __init__(self, d):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(d, d, 3, padding=1), nn.GELU(), nn.Conv1d(d, d, 3, padding=1), nn.GELU())
        self.mlp = nn.Sequential(nn.Linear(d * 3, d), nn.GELU(), nn.Linear(d, 1))

    def forward(self, h):
        c = self.conv(h.transpose(1, 2)).transpose(1, 2)
        a = c[:, :-1]
        b = c[:, 1:]
        feat = torch.cat([a, b, torch.abs(a - b)], dim=-1)
        return self.mlp(feat).squeeze(-1)

class WorkflowTransitionContrastive(nn.Module):
    """
        Self-supervised transition model.

        source segment → expected next segment representation

        같은 mini-batch의 다른 target segment를 contrastive negatives로 사용한다.
        실제 업무명 / 메뉴 / API 의미 mapping은 사용하지 않는다.
        """

    def __init__(self, d):
        super().__init__()
        self.source_encoder = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.LayerNorm(d), nn.Linear(d, d))
        self.target_encoder = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.LayerNorm(d), nn.Linear(d, d))

    def encode_source(self, x):
        return F.normalize(self.source_encoder(x), dim=-1)

    def encode_target(self, x):
        return F.normalize(self.target_encoder(x), dim=-1)

    def forward(self, source, target):
        return (self.encode_source(source), self.encode_target(target))

def _robust_surprise_to_score(values):
    values = np.asarray(values, dtype=np.float32)
    if len(values) == 0:
        return values
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    scale = max(1.4826 * mad, 0.001)
    z = (values - med) / scale
    return (1.0 / (1.0 + np.exp(-np.clip(z, -12, 12)))).astype(np.float32)

class NeuralPrototypeModel(nn.Module):

    def __init__(self, input_dim, k, latent_dim=64):
        super().__init__()
        self.projector = nn.Sequential(nn.Linear(input_dim, input_dim), nn.GELU(), nn.Dropout(0.15), nn.Linear(input_dim, latent_dim))
        self.prototypes = nn.Parameter(torch.randn(k, latent_dim))

    def forward(self, x, temp=0.15):
        z = F.normalize(self.projector(x), dim=-1)
        p = F.normalize(self.prototypes, dim=-1)
        return (z, z @ p.T / temp)

def _assignment_feature(runs):
    """
    Seed별 prototype label 번호는 서로 비교할 수 없으므로,
    각 seed assignment를 one-hot으로 바꾸어 이어 붙인다.

    Euclidean distance는 여러 seed에서 얼마나 자주 같은 prototype에
    묶였는지를 label permutation과 무관하게 반영한다.
    """
    if not runs:
        return np.empty((0, 0), dtype=np.float32)
    features = []
    for run in runs:
        a = np.asarray(run['assignment'], dtype=int)
        k = int(run['k'])
        onehot = np.zeros((len(a), max(k, 1)), dtype=np.float32)
        if len(a):
            onehot[np.arange(len(a)), a] = 1.0
        features.append(onehot)
    x = np.concatenate(features, axis=1)
    x /= math.sqrt(max(len(features), 1))
    return x

def _within_seed_agreement(labels, runs):
    """
    consensus cluster 내부의 item pair가 원래 seed prototype에서도
    같이 묶이는 비율.
    """
    labels = np.asarray(labels, dtype=int)
    numer = 0.0
    denom = 0.0
    for cluster_id in np.unique(labels):
        ids = np.flatnonzero(labels == cluster_id)
        m = len(ids)
        if m < 2:
            continue
        pair_total = m * (m - 1) / 2
        for run in runs:
            a = np.asarray(run['assignment'])[ids]
            counts = np.bincount(a, minlength=max(int(run['k']), 1))
            same = float((counts * (counts - 1) / 2).sum())
            numer += same
            denom += pair_total
    return float(numer / denom) if denom > 0 else 1.0

def _cluster_balance_entropy(labels):
    labels = np.asarray(labels, dtype=int)
    if len(labels) == 0:
        return 0.0
    counts = np.bincount(labels)
    counts = counts[counts > 0]
    if len(counts) <= 1:
        return 0.0
    p = counts / counts.sum()
    return float(-(p * np.log(p)).sum() / math.log(len(counts)))

def _small_cluster_share(labels, min_support):
    labels = np.asarray(labels, dtype=int)
    if len(labels) == 0:
        return 1.0
    counts = np.bincount(labels)
    small_ids = np.flatnonzero(counts < min_support)
    return float(np.isin(labels, small_ids).mean())

def _fit_agglomerative(x, k):
    try:
        model = AgglomerativeClustering(n_clusters=int(k), linkage='ward')
        return model.fit_predict(x)
    except TypeError:
        model = AgglomerativeClustering(n_clusters=int(k), linkage='ward')
        return model.fit_predict(x)

def _consensus_k_search(feature, runs, k_min, k_max, prefix, min_support):
    n = len(feature)
    if n == 0:
        return (np.array([], dtype=int), pd.DataFrame(), {'k': 0, 'score': None})
    k_min = max(2, min(int(k_min), n))
    k_max = max(k_min, min(int(k_max), n))
    rows = []
    candidates = {}
    for k in range(k_min, k_max + 1):
        labels = _fit_agglomerative(feature, k)
        candidates[k] = labels
        if len(np.unique(labels)) > 1 and len(labels) > len(np.unique(labels)):
            sample_size = min(1500, len(labels))
            sil = float(silhouette_score(feature, labels, metric='euclidean', sample_size=sample_size if sample_size < len(labels) else None, random_state=SEED))
        else:
            sil = -1.0
        within = _within_seed_agreement(labels, runs)
        entropy = _cluster_balance_entropy(labels)
        small_share = _small_cluster_share(labels, min_support)
        sil01 = (sil + 1.0) / 2.0
        score = 0.5 * sil01 + 0.35 * within + 0.15 * entropy - 0.3 * small_share
        rows.append({'level': prefix, 'k': int(k), 'silhouette': sil, 'within_seed_agreement': within, 'balance_entropy': entropy, 'small_cluster_share': small_share, 'consensus_score': float(score)})
    search_df = pd.DataFrame(rows)
    best_row = search_df.sort_values(['consensus_score', 'within_seed_agreement', 'silhouette'], ascending=[False, False, False]).iloc[0]
    best_k = int(best_row['k'])
    labels = np.asarray(candidates[best_k], dtype=int)
    counts = Counter(labels.tolist())
    ordered = [old for (old, _) in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    remap = {old: new for (new, old) in enumerate(ordered)}
    labels = np.asarray([remap[int(x)] for x in labels], dtype=int)
    summary = {'k': best_k, 'score': float(best_row['consensus_score']), 'silhouette': float(best_row['silhouette']), 'within_seed_agreement': float(best_row['within_seed_agreement']), 'balance_entropy': float(best_row['balance_entropy']), 'small_cluster_share': float(best_row['small_cluster_share'])}
    return (labels, search_df, summary)

def _consensus_item_metrics(feature, labels):
    labels = np.asarray(labels, dtype=int)
    if len(labels) == 0:
        return (np.array([], dtype=np.float32), np.array([], dtype=np.float32))
    unique = np.unique(labels)
    centroids = []
    for c in unique:
        centroids.append(feature[labels == c].mean(axis=0))
    centroids = np.asarray(centroids, dtype=np.float32)
    fnorm = feature / np.maximum(np.linalg.norm(feature, axis=1, keepdims=True), 1e-08)
    cnorm = centroids / np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-08)
    sim = fnorm @ cnorm.T
    own = np.zeros(len(labels), dtype=np.float32)
    margin = np.zeros(len(labels), dtype=np.float32)
    cluster_to_pos = {int(c): i for (i, c) in enumerate(unique)}
    for (i, c) in enumerate(labels):
        pos = cluster_to_pos[int(c)]
        own[i] = sim[i, pos]
        if sim.shape[1] >= 2:
            others = np.delete(sim[i], pos)
            second = float(others.max())
        else:
            second = 0.0
        margin[i] = own[i] - second
    confidence = np.clip(own, 0.0, 1.0)
    return (confidence.astype(np.float32), margin.astype(np.float32))
