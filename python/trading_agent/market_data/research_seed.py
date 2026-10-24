"""Read-only research handoff for the pre-existing authenticated Kronos/Shadow archive.

No broker access, no writes, no freshness upgrade, no feed substitution, no M03-B
activation. The underlying verifier enforces the content-addressed Shadow proof.
"""
from dataclasses import dataclass

from trading_agent.core_v3.contracts import require


@dataclass(frozen=True, slots=True)
class ResearchSeed:
    timeframe: str
    as_of: str
    source_sha256: str
    shadow_event_hash: str
    bars: tuple
    provenance: str = 'AUTHENTIC_IBKR_PAPER_SHADOW_ARCHIVE'
    destination: str = 'RESEARCH_ONLY_NOT_MARKET_FEED'
    execution_authorized: bool = False


def verified_shadow_research_seed(root, shadow_source, config):
    """Derive a labelled historical seed using Kronos's existing SHA verification.

    The returned historical snapshot is deliberately not sent to a live quote,
    trading, Core, or Market Analyst API. A separate M03-B contract is required.
    """
    from trading_agent.kronos.persistence import source_request

    request = source_request(root, shadow_source, config)
    provenance = request.get('source', {})
    require(provenance.get('quality') == 'AUTHENTIC' and
            provenance.get('provider') == 'IBKR_PAPER_MIDPOINT' and
            type(request.get('bars')) is list and
            request.get('timeframe') in ('15m','1H','4H') and
            type(request.get('as_of')) is str, 'M035_SHADOW_SOURCE_INVALID')
    for key in ('sha256','event_hash'):
        value = provenance.get(key)
        require(type(value) is str and len(value) == 64 and
                all(c in '0123456789abcdef' for c in value),
                'M035_SHADOW_PROVENANCE_INVALID')
    return ResearchSeed(request['timeframe'],request['as_of'],provenance['sha256'],
                        provenance['event_hash'],tuple(request['bars']))
