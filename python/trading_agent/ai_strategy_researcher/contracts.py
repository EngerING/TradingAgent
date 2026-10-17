"""Closed declarative language. Model text is data, never Python or authorization."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import re

RATES=(1,2,3,5,7.5,10,12.5,15)
MODELS=('TIERED_BASE','TIERED_SPREAD_SLIPPAGE_STRESS','FIXED_FEE_STRESS')
SYMBOLS=('F','SPY')
PATTERNS=('TREND_CROSS','PULLBACK','BREAKOUT','MEAN_REVERSION')
ENGINE='AI_STRATEGY_SIMULATION_V1'
FOLDS=(('development','2021-01-01','2022-01-01'),
       ('validation','2022-01-01','2024-01-01'),
       ('wf1','2022-01-01','2022-07-01'),
       ('wf2','2022-07-01','2023-01-01'),
       ('wf3','2023-01-01','2024-01-01'))


def utc():return datetime.now(timezone.utc).isoformat()


def number(value):
    if isinstance(value,bool):raise ValueError('NUMBER_REQUIRED')
    n=Decimal(str(value))
    if not n.is_finite() or abs(n)>Decimal('1e12'):raise ValueError('FINITE_NUMBER_REQUIRED')
    return n


def at(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('UTC_REQUIRED')
    return t.astimezone(timezone.utc)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()


def strict_json(raw):
    def pairs(items):
        r={}
        for k,v in items:
            if k in r:raise ValueError('DUPLICATE_JSON_KEY')
            r[k]=v
        return r
    def bad(v):raise ValueError('NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)


def exact(value,keys):
    if type(value) is not dict or set(value)!=set(keys):raise ValueError('UNEXPECTED_FIELDS')


def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('INTEGER_OUT_OF_RANGE')
    return value


def text(value,maximum):
    if not isinstance(value,str) or not value.strip() or len(value.encode('utf-8'))>maximum:
        raise ValueError('TEXT_OUT_OF_RANGE')
    if re.search(r'sk-[A-Za-z0-9_-]{8,}|\b(?:DU|U)\d{5,}|Bearer\s+\S+',value):
        raise ValueError('SENSITIVE_OUTPUT_REJECTED')
    return value


NAME_PATTERN=r'^[A-Za-z][A-Za-z0-9_]{2,48}$'
INTEGER_LIMITS={'fast':(3,40),'slow':(5,100),'lookback':(10,100),
    'atr_period':(5,30),'max_hold_bars':(2,40)}
NUMBER_LIMITS={'stop_atr':(.5,4),'target_r':(.5,5),'risk_percent':(1,15)}
CANDIDATE_PROPERTIES={
    'name':{'type':'string','pattern':NAME_PATTERN},'symbol':{'type':'string','enum':list(SYMBOLS)},
    'timeframe_minutes':{'type':'integer','enum':[60,1440]},
    'pattern':{'type':'string','enum':list(PATTERNS)},
    **{k:{'type':'integer','minimum':lo,'maximum':hi} for k,(lo,hi) in INTEGER_LIMITS.items()},
    **{k:{'type':'number','minimum':lo,'maximum':hi} for k,(lo,hi) in NUMBER_LIMITS.items()}}
CANDIDATE_PROPERTIES['risk_percent']['enum']=list(RATES)
SCHEMA={'type':'object','additionalProperties':False,
    'properties':{'hypothesis':{'type':'string'},'rationale':{'type':'string'},
        'evidence_ids':{'type':'array','minItems':1,'maxItems':8,'items':{'type':'string'}},
        'candidate':{'type':'object','additionalProperties':False,
            'properties':CANDIDATE_PROPERTIES,'required':list(CANDIDATE_PROPERTIES)}},
    'required':['hypothesis','rationale','evidence_ids','candidate']}
PLAN_TEXT_FIELDS=('problem','prior_failure_analysis','novelty','why_evaluate','insufficient_evidence','refutation_test','alternatives')
PLAN_SCHEMA={'type':'object','additionalProperties':False,'properties':{
    **{k:{'type':'string'} for k in PLAN_TEXT_FIELDS},
    'action':{'type':'string','enum':['PROPOSE_EXPERIMENT','DEFER_RESEARCH']},
    'prior_evidence_ids':{'type':'array','maxItems':8,'items':{'type':'string'}},
    'changed_fields':{'type':'array','maxItems':12,'items':{'type':'string','enum':[k for k in CANDIDATE_PROPERTIES if k!='name']}}},
    'required':list(PLAN_TEXT_FIELDS)+['action','prior_evidence_ids','changed_fields']}


class ProposalValidationError(ValueError):
    """Only fixed codes/paths cross the journal boundary; never values or raw exceptions."""
    def __init__(self,code,field,category):
        super().__init__(code);self.code=code;self.field=field;self.category=category

    def diagnostic(self):
        return dict(validation_code=self.code,field=self.field,category=self.category)


def checked(check,field,category,*args):
    try:return check(*args)
    except (ValueError,TypeError,ArithmeticError) as exc:
        allowed={'UNEXPECTED_FIELDS','TEXT_OUT_OF_RANGE','SENSITIVE_OUTPUT_REJECTED',
            'INTEGER_OUT_OF_RANGE','NUMBER_REQUIRED','FINITE_NUMBER_REQUIRED'}
        fallback='TEXT_OUT_OF_RANGE' if check is text else 'NUMBER_REQUIRED'
        code=exc.args[0] if exc.args and type(exc.args[0]) is str and exc.args[0] in allowed else fallback
        raise ProposalValidationError(code,field,category) from None


def parse_proposal(raw,evidence_ids):
    try:valid=type(raw) is str and len(raw.encode('utf-8'))<=20000
    except UnicodeError:valid=False
    if not valid:
        raise ProposalValidationError('PROPOSAL_TEXT_INVALID','$','FORMAT')
    try:value=strict_json(raw)
    except (ValueError,TypeError) as exc:
        code=exc.args[0] if exc.args and exc.args[0] in ('DUPLICATE_JSON_KEY','NONFINITE_JSON') else 'JSON_SYNTAX_INVALID'
        raise ProposalValidationError(code,'$','FORMAT') from None
    return validate_proposal(value,evidence_ids)


def validate_proposal(value,evidence_ids):
    keys=SCHEMA['required']+(['research_plan'] if type(value) is dict and 'research_plan' in value else [])
    checked(exact,'$','FORMAT',value,keys)
    for k,limit in (('hypothesis',1000),('rationale',2000)):
        checked(text,'$.'+k,'FORMAT',value[k],limit)
    refs=value['evidence_ids']
    if type(refs) is not list or not 1<=len(refs)<=8 or any(type(x) is not str or x not in evidence_ids for x in refs):
        raise ProposalValidationError('AUTHENTIC_EVIDENCE_REFERENCE_REQUIRED','$.evidence_ids','EVIDENCE')
    if 'research_plan' in value:validate_research_plan(value['research_plan'],evidence_ids)
    if value['candidate'] is None and value.get('research_plan',{}).get('action')=='DEFER_RESEARCH':return value
    if value.get('research_plan',{}).get('action')=='DEFER_RESEARCH':
        raise ProposalValidationError('DEFER_REQUIRES_NO_CANDIDATE','$.candidate','FORMAT')
    c=value['candidate'];checked(exact,'$.candidate','FORMAT',c,CANDIDATE_PROPERTIES)
    if type(c['name']) is not str or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,48}',c['name']) is None:
        raise ProposalValidationError('CANDIDATE_IDENTIFIER_REQUIRED','$.candidate.name','PARAMETER')
    checked(text,'$.candidate.name','PARAMETER',c['name'],49)
    for k,allowed in (('symbol',SYMBOLS),('pattern',PATTERNS),('timeframe_minutes',(60,1440))):
        if c[k] not in allowed or (k=='timeframe_minutes' and type(c[k]) is not int):
            raise ProposalValidationError('RESEARCH_SCOPE_REQUIRED','$.candidate.'+k,'PARAMETER')
    for k,(lo,hi) in INTEGER_LIMITS.items():
        checked(integer,'$.candidate.'+k,'PARAMETER',c[k],lo,hi)
    if c['fast']>=c['slow']:
        raise ProposalValidationError('CAUSAL_WINDOWS_REQUIRED','$.candidate.fast','PARAMETER')
    for k,(lo,hi) in NUMBER_LIMITS.items():
        if type(c[k]) not in (int,float,Decimal):
            raise ProposalValidationError('NUMBER_REQUIRED','$.candidate.'+k,'PARAMETER')
        n=checked(number,'$.candidate.'+k,'PARAMETER',c[k])
        if not number(lo)<=n<=number(hi):
            raise ProposalValidationError('RESEARCH_PARAMETER_RANGE','$.candidate.'+k,'PARAMETER')
    if number(c['risk_percent']) not in [number(x) for x in RATES]:
        raise ProposalValidationError('REGISTERED_RISK_GRID_REQUIRED','$.candidate.risk_percent','PARAMETER')
    return value


def validate_research_plan(plan,evidence_ids):
    checked(exact,'$.research_plan','FORMAT',plan,PLAN_SCHEMA['required'])
    for k in PLAN_TEXT_FIELDS:checked(text,'$.research_plan.'+k,'FORMAT',plan[k],400)
    if plan['action'] not in ('PROPOSE_EXPERIMENT','DEFER_RESEARCH'):
        raise ProposalValidationError('RESEARCH_PLAN_ACTION_REQUIRED','$.research_plan.action','FORMAT')
    for k,allowed,maximum in [('prior_evidence_ids',evidence_ids,8),('changed_fields',CANDIDATE_PROPERTIES,12)]:
        values=plan[k]
        if type(values) is not list or len(values)>maximum or any(type(x) is not str or x not in allowed or (k=='changed_fields' and x=='name') for x in values) or len(set(values))!=len(values):
            raise ProposalValidationError('RESEARCH_PLAN_REFERENCES_REQUIRED','$.research_plan.'+k,'EVIDENCE')
    if plan['action']=='DEFER_RESEARCH' and plan['changed_fields']:
        raise ProposalValidationError('DEFER_REQUIRES_NO_CHANGES','$.research_plan.changed_fields','FORMAT')


def candidate_version(candidate):
    # Renaming the same behavior is not a new experiment or an escape from deduplication.
    specification={k:v for k,v in candidate.items() if k!='name'}
    return digest({'engine':ENGINE,'specification':specification,'side':'LONG','exposure':1})
