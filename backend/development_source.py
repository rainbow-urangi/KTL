"""현재 실제 DEVELOPMENT dataset의 경량 준비 상태."""
from .model_runner import DATASET
from .registry import EXTERNAL

class DevelopmentDataSource:
    dataset_id=DATASET
    source_type='DEVELOPMENT'
    def __init__(self,root):self.root=root;self.sources={};self.m02_aliases=None
    def prepare(self,metric):
        if metric in EXTERNAL:status='EXTERNAL_MODULE_PENDING';missing=['외부 결과 수신 대기']
        elif metric in {'M02','M06'}:status='READY';missing=[]
        else:status='NOT_CONFIGURED';missing=['이번 DEVELOPMENT 연결 범위는 M02/M06 및 외부 결과 수신입니다.']
        return {'status':status,'inputs':None,'details':{'missing':missing,'notice':'DEVELOPMENT DATASET · 공식 시험성적 아님'}}
