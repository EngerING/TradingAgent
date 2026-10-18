"""Fixed offline adapter; no dynamic code, transports, credentials or plugins."""
from dataclasses import dataclass
import hashlib
from typing import Protocol

from .contracts import ContractError, content_hash, require
from .research_contracts import DesignReceipt, DesignRequest, ResearchInputs, ResearchProposal


class ResearchDesigner(Protocol):
    def propose(self, request: DesignRequest) -> str: ...


def proposal_for(request: DesignRequest) -> ResearchProposal:
    fingerprint = content_hash(request.request)
    return ResearchProposal('candidate-' + fingerprint[:32], fingerprint,
        request.request.instrument.content_sha256, request.preflight.witness)


@dataclass(frozen=True, slots=True)
class SimulatedDesigner:
    """A closed fixture adapter, deliberately the only runner-accepted implementation."""
    proposal_json: str | None = None

    def __post_init__(self):
        require(self.proposal_json is None or (type(self.proposal_json) is str
                and len(self.proposal_json) <= 32768), 'SIMULATED_FIXTURE_INVALID')

    def propose(self, request: DesignRequest) -> str:
        require(type(request) is DesignRequest, 'DESIGN_REQUEST_REQUIRED')
        return proposal_for(request).to_json() if self.proposal_json is None else self.proposal_json


def receipt(raw, request: DesignRequest) -> DesignReceipt:
    """Reject untrusted output without copying invalid text into diagnostics/storage."""
    encoded = b'INVALID_OUTPUT'
    proposal = None
    try:
        require(type(raw) is str and len(raw) <= 32768, 'PROPOSAL_SIZE_INVALID')
        encoded = raw.encode('utf-8')
        require(len(encoded) <= 32768, 'PROPOSAL_SIZE_INVALID')
        parsed = ResearchProposal.from_json(raw)
        require(parsed == proposal_for(request), 'PROPOSAL_BINDING_MISMATCH')
        proposal = parsed
    except (ContractError, UnicodeError):
        pass
    return DesignReceipt(hashlib.sha256(encoded).hexdigest(), proposal)


@dataclass(slots=True)
class OfflineInputSource:
    """Host-published immutable inputs, not a fresh/authenticated market capture."""
    inputs: ResearchInputs

    def capture(self) -> ResearchInputs:
        value = self.inputs
        require(type(value) is ResearchInputs, 'OFFLINE_INPUTS_REQUIRED')
        return value
