from datetime import date
from pathlib import Path
import re
from .contracts import exact,integer,number,strict_json

KEYS=('model','max_provider_calls','max_candidates','max_backtests','max_seconds',
      'provider_timeout_seconds','simulation_timeout_seconds','max_output_tokens','max_total_tokens',
      'max_cost_usd','max_prompt_bytes','max_consecutive_provider_failures','pricing')


def validate_config(c,online=False):
    exact(c,KEYS)
    if type(c['model']) is not str or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}',c['model']):
        raise ValueError('MODEL_REQUIRED')
    for name,lo,hi in [('max_provider_calls',1,100),('max_candidates',1,30),('max_backtests',15,450),
        ('max_seconds',5,7200),('provider_timeout_seconds',1,60),('simulation_timeout_seconds',1,120),
        ('max_output_tokens',512,8192),('max_total_tokens',512,2_000_000),('max_prompt_bytes',1000,40000),
        ('max_consecutive_provider_failures',1,3)]:integer(c[name],lo,hi)
    if not 0<number(c['max_cost_usd'])<=100:raise ValueError('BOUNDED_RESEARCH_COST_REQUIRED')
    p=c['pricing'];exact(p,('model','input_usd_per_million','output_usd_per_million','verified_on','source'))
    if p['model']!=c['model']:raise ValueError('MODEL_PRICE_BINDING_REQUIRED')
    for k in ('input_usd_per_million','output_usd_per_million'):
        if not 0<number(p[k])<=1000:raise ValueError('TOKEN_PRICE_REQUIRED')
    if p['source']!='https://developers.openai.com/api/docs/pricing':raise ValueError('OFFICIAL_PRICE_SOURCE_REQUIRED')
    age=(date.today()-date.fromisoformat(p['verified_on'])).days
    if online and not 0<=age<=30:raise ValueError('REVERIFY_MODEL_PRICE_CEILINGS')
    return c


def load(root,online=False):
    return validate_config(strict_json((Path(root)/'config/ai-strategy-research.json').read_bytes()),online)


def estimated_cost(config,input_tokens,output_tokens):
    p=config['pricing']
    return (input_tokens*number(p['input_usd_per_million'])+output_tokens*number(p['output_usd_per_million']))/1_000_000
