"""Pure bounded inspection. Real-provider schema closure remains explicitly pending."""
from datetime import timedelta
import hashlib

from ..contracts import ContractError, content_hash, require, utc
from .canonical_csv import parse
from .contracts import MAX_BYTES, DatasetSpec, ReviewReceipt, SessionCalendar
from .records import IngestionManifest, IngestionResult, Issue, QualityReport, records_hash
from .time_rules import expected_intervals, load_zone, session_windows


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _quality(records, spec, calendar):
    issues, seen_ids, seen_events = [], set(), set()
    windows = session_windows(calendar, spec.window_start, spec.window_end)
    expected = expected_intervals(calendar, spec.window_start, spec.window_end,
                                  spec.interval_seconds) if spec.kind == 'OHLC' else None
    expected_set = set(expected or ())
    previous, previous_available = None, None
    for record in records:
        def issue(code):
            if len(issues) < 120:
                issues.append(Issue(record.row_number, code))
        if record.record_id in seen_ids:
            issue('H38_DUPLICATE_ID')
        seen_ids.add(record.record_id)
        event = ((record.opened_at, record.closed_at) if spec.kind == 'OHLC'
                 else (record.event_at, record.sequence))
        if event in seen_events:
            issue('H38_DUPLICATE_EVENT')
        seen_events.add(event)
        if previous is not None and event <= previous:
            issue('H38_EVENT_ORDER')
        if previous_available is not None and record.available_at < previous_available:
            issue('H38_AVAILABILITY_ORDER')
        previous, previous_available = event, record.available_at
        if spec.kind == 'OHLC':
            if event not in expected_set:
                issue('H38_SESSION_ALIGNMENT')
        elif not any(begin <= record.event_at < finish for begin, finish, _ in windows):
            issue('H38_OUTSIDE_SESSION')
    if expected is not None:
        gaps = len(expected_set-seen_events)
    else:
        # A silence threshold is a quality rule, not proof of tick-feed completeness.
        gaps = 0
        limit = timedelta(seconds=spec.quote_max_gap_seconds)
        for begin, finish, _ in windows:
            events = sorted(r.event_at for r in records if begin <= r.event_at < finish)
            points = [begin, *events, finish]
            gaps += (1 if not events else sum(b-a > limit for a, b in zip(points, points[1:])))
    if gaps:
        issues.append(Issue(0, 'H38_GAP'))
    if not windows:
        issues.append(Issue(0, 'H38_NO_SESSION'))
    return issues, None if expected is None else len(expected), gaps


def ingest_canonical(raw, spec, calendar, tzif, evidence, reviews=(), *, cutoff):
    """Only canonical synthetic fixtures can become inspection-ready in this phase.

    Reviews come from the trusted host after independent external reconciliation;
    nothing in raw/spec/evidence is interpreted as authorization or a review.
    """
    require(type(spec) is DatasetSpec and type(calendar) is SessionCalendar, 'H38_INPUT_TYPES')
    require(type(reviews) is tuple and len(reviews) <= 32
            and all(type(r) is ReviewReceipt for r in reviews), 'H38_HOST_REVIEWS')
    for data in (raw, tzif, evidence):
        require(type(data) is bytes and len(data) <= MAX_BYTES, 'H38_INPUT_SIZE')
    cutoff = utc(cutoff)
    issues, records, count, complete, expected, gaps = [], (), 0, False, None, 0
    for actual, declared, code in (
        (sha256(raw), spec.raw_sha256, 'H38_RAW_HASH'),
        (content_hash(calendar), spec.calendar_sha256, 'H38_CALENDAR_HASH'),
        (sha256(tzif), spec.tzif_sha256, 'H38_TZIF_HASH'),
        (sha256(evidence), spec.evidence_sha256, 'H38_EVIDENCE_HASH')):
        if actual != declared:
            issues.append(Issue(0, code))
    if not evidence:
        issues.append(Issue(0, 'H38_EVIDENCE_REQUIRED'))
    if sha256(evidence) == sha256(raw):
        issues.append(Issue(0, 'H38_SELF_EVIDENCE'))
    if calendar.evidence_sha256 != spec.evidence_sha256:
        issues.append(Issue(0, 'H38_CALENDAR_EVIDENCE'))
    if spec.observed_at > cutoff:
        issues.append(Issue(0, 'H38_OBSERVED_AFTER_CUTOFF'))
    matched = tuple(r for r in reviews if r.provider_id == spec.provider_id
        and r.export_id == spec.export_id and r.descriptor_sha256 == content_hash(spec)
        and r.evidence_sha256 == spec.evidence_sha256 and spec.observed_at <= r.reviewed_at <= cutoff)
    review = matched[0] if len(matched) == 1 else None
    if review is None:
        issues.append(Issue(0, 'H38_REVIEW_REQUIRED' if not matched else 'H38_AMBIGUOUS_REVIEW'))
    if spec.data_origin == 'PROVIDER_EXPORT' or not spec.provider_id.startswith('fixture-'):
        # A generic fixture schema must not silently masquerade as a provider adapter.
        issues.append(Issue(0, 'H38_PROVIDER_FORMAT_UNVERIFIED'))
    else:
        try:
            require(calendar.timezone_name == spec.timezone_name, 'H38_CALENDAR_ZONE')
            zone = load_zone(tzif, spec.timezone_name)
            for session in calendar.sessions:
                require(session.opened_at.astimezone(zone).date().isoformat() == session.opening_date,
                        'H38_SESSION_DATE_ZONE')
            records, parse_issues, count, complete = parse(raw, spec, zone)
            issues.extend(parse_issues)
            quality, expected, gaps = _quality(records, spec, calendar)
            issues.extend(quality)
        except ContractError as error:
            issues.append(Issue(0, str(error)))
        except OverflowError:
            issues.append(Issue(0, 'H38_TIMESTAMP_RANGE'))
    if len(issues) > 256:
        issues = issues[:255] + [Issue(0, 'H38_ISSUE_LIMIT')]
    report = QualityReport(count, len(records), complete, expected, gaps, tuple(issues))
    manifest = IngestionManifest('QUARANTINED' if issues else 'READY_FOR_INSPECTION', spec.data_origin,
        sha256(raw), content_hash(spec), content_hash(calendar), sha256(tzif), sha256(evidence),
        None if review is None else content_hash(review), records_hash(records), content_hash(report),
        count, cutoff, 'REAL_HISTORICAL_UNVERIFIED' if spec.data_origin == 'PROVIDER_EXPORT'
        else 'SYNTHETIC_TEST_FIXTURE', 'UNREVIEWED' if review is None else 'LOCAL_REVIEW_ATTESTED')
    return IngestionResult(manifest, report, () if issues else records)
