"""CPU 단방향 GRU 경계 모델. 학습 label과 추론 입력은 분리됩니다."""
import random
import numpy as np
import torch
from torch import nn
from .features import features

class BoundaryGRU(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.projection=nn.Sequential(nn.Linear(config['hash_dim']+config['previous_hash_dim']+12,config['projection_dim']),nn.Tanh())
        self.gru=nn.GRU(config['projection_dim'],config['hidden_dim'],config['layers'],batch_first=True,
                        dropout=config['dropout'] if config['layers']>1 else 0)
        self.head=nn.Sequential(nn.Linear(config['hidden_dim'],32),nn.ReLU(),nn.Dropout(config['dropout']),nn.Linear(32,1))
    def forward(self,x):
        h,_=self.gru(self.projection(x))
        return self.head(h).squeeze(-1),h

def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)

def train(chunks, config):
    """chunks contain only train events; first transition in each chunk is unscored."""
    seed_all(config['seed'])
    model=BoundaryGRU(config)
    data=[]
    for events, labels in chunks:
        if len(events)>1:
            data.append((torch.from_numpy(features(events,config))[None],torch.tensor(labels,dtype=torch.float32)[None]))
    pos=sum(float(y[:,1:].sum()) for _,y in data)
    neg=sum(y.numel()-1 for _,y in data)-pos
    if not pos or not neg:raise ValueError('Both boundary classes required')
    weight=neg/pos
    criterion=nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight),reduction='sum')
    optimizer=torch.optim.Adam(model.parameters(),lr=config['learning_rate'])
    history=[]
    for epoch in range(config['epochs']):
        model.train();optimizer.zero_grad();losses=[]
        for x,y in data:
            logits,_=model(x);losses.append(criterion(logits[:,1:],y[:,1:]))
        loss=sum(losses)/(pos+neg)
        loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        history.append({'epoch':epoch+1,'loss':float(loss.detach())})
    model.eval()
    return model,dict(positive=int(pos),negative=int(neg),pos_weight=weight,history=history)

def predict(model, streams, config):
    model.eval();outputs=[]
    with torch.no_grad():
        for stream in streams:
            logits,h=model(torch.from_numpy(features(stream,config))[None])
            prob=torch.sigmoid(logits)[0].numpy()
            prob[0]=0.0
            outputs.append((prob,h[0].numpy()))
    return outputs

def save_model(model,path):
    torch.save(model.state_dict(),path)

def load_model(path,config):
    model=BoundaryGRU(config)
    model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
    model.eval();return model
