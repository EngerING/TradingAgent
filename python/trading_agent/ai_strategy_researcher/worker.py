"""Fixed worker entry point, stdin JSON only. Never evaluates generated source."""
import sys
from .contracts import strict_json,encoded,validate_proposal
from .providers import openai_response
from .simulation import evaluate


def main():
    raw=sys.stdin.buffer.read(12_000_001)
    if len(raw)>12_000_000:raise ValueError('WORKER_INPUT_TOO_LARGE')
    payload=strict_json(raw)
    if sys.argv[1:] == ['provider']:
        result=openai_response(payload['body'],payload['timeout'])
    elif sys.argv[1:] == ['simulation']:
        validate_proposal(payload['proposal'],payload['evidence_ids'])
        if payload['candidate']!=payload['proposal']['candidate']:raise ValueError('BOUND_CANDIDATE_REQUIRED')
        result=evaluate(payload)
    else:raise ValueError('WORKER_KIND_FORBIDDEN')
    sys.stdout.buffer.write(encoded(result));sys.stdout.flush()


if __name__=='__main__':
    try:main()
    except Exception:
        # No traceback, request content, credential or raw provider exception crosses this boundary.
        sys.stdout.buffer.write(encoded(dict(worker_error='CONTROLLED_WORKER_FAILED')))
        sys.exit(2)
