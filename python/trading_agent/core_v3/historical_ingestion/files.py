"""Bounded local snapshots and new, content-addressed custody directories only."""
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from ..contracts import canonical_bytes, content_hash, require
from .contracts import MAX_BYTES, DatasetSpec, SessionCalendar
from .ingestion import ingest_canonical, sha256


INPUT_NAMES = ('raw.csv', 'descriptor.json', 'calendar.json', 'timezone.tzif', 'evidence.bin')
ARCHIVE_LIMIT = 16 * MAX_BYTES


def _component(name):
    require(name not in ('', '.', '..') and name == name.rstrip(' .')
            and name.casefold() != '.local' and not any(c in name for c in '\\/:<>?"*|')
            and not any(ord(c) < 32 for c in name), 'H38_LOCAL_PATH')
    base = name.split('.')[0].upper()
    require(base not in ('CON', 'PRN', 'AUX', 'NUL')
            and re.fullmatch(r'(?:COM|LPT)[0-9¹²³]', base) is None, 'H38_DEVICE_PATH')


def safe_path(value):
    """Reject UNC, devices, alternate streams, .local and all reparse components."""
    path = Path(value)
    require(path.is_absolute() and not str(path).startswith(('\\\\', '//'))
            and not path.drive.startswith('\\'), 'H38_ABSOLUTE_LOCAL_PATH')
    for part in path.parts[1:]:
        _component(part)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024),
                'H38_LINK_FORBIDDEN')
    require(not any(p.casefold().rstrip(' .') == '.local' for p in path.resolve().parts), 'H38_PRIVATE_PATH')
    return path


def read_local(root, name, *, max_bytes=MAX_BYTES):
    require(type(name) is str and '\\' not in name, 'H38_RELATIVE_PATH')
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.parts, 'H38_RELATIVE_PATH')
    # Check the literal split as PurePath would erase '.' and repeated separators.
    for component in name.split('/'):
        _component(component)
    root = safe_path(root)
    path = safe_path(root.joinpath(*relative.parts))
    require(root.is_dir() and type(max_bytes) is int and 0 < max_bytes <= ARCHIVE_LIMIT, 'H38_FILE_POLICY')
    require(path.is_file(), 'H38_REGULAR_FILE_REQUIRED')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= max_bytes, 'H38_FILE_SIZE')
    require(before.st_nlink == 1, 'H38_HARDLINK_FORBIDDEN')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'H38_FILE_CHANGED')
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1, 'H38_FILE_CHANGED')
        raw = stream.read(max_bytes+1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= max_bytes and (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns) and len(raw) == after.st_size,
            'H38_FILE_CHANGED')
    return raw


def _snapshot(root):
    return {name: read_local(root, name) for name in INPUT_NAMES}


def _inspect(inputs, reviews, cutoff):
    return ingest_canonical(inputs['raw.csv'], DatasetSpec.from_json(inputs['descriptor.json']),
        SessionCalendar.from_json(inputs['calendar.json']), inputs['timezone.tzif'], inputs['evidence.bin'],
        reviews, cutoff=cutoff)


def ingest_local(input_root, *, reviews=(), cutoff):
    return _inspect(_snapshot(input_root), reviews, cutoff)


def _bundle(inputs, result, reviews):
    return inputs | {
        'manifest.json': canonical_bytes(result.manifest),
        'report.json': canonical_bytes(result.report),
        'review_audit.json': canonical_bytes({'notice': 'AUDIT_COPY_NOT_A_TRUST_SOURCE',
                                            'host_reviews': [r.to_dict() for r in reviews]}),
        'normalized.jsonl': b''.join(canonical_bytes(r)+b'\n' for r in result.records)}


def _index(files):
    return canonical_bytes({'schema': 'trading.core_v3.historical.custody_index', 'schema_version': 1,
        'notice': 'BYTE_INTEGRITY_IS_NOT_PROVIDER_AUTHENTICITY',
        'files': {name: {'sha256': sha256(raw), 'bytes': len(raw)} for name, raw in files.items()}})


def _verify_bytes(target, files):
    target = safe_path(target)
    index = _index(files)
    require(target.name == sha256(index) and target.is_dir(), 'H38_ARCHIVE_ID')
    expected = files | {'file_index.json': index}
    require({p.name for p in target.iterdir()} == set(expected), 'H38_ARCHIVE_FILES')
    for name, raw in expected.items():
        require(read_local(target, name, max_bytes=ARCHIVE_LIMIT) == raw, 'H38_ARCHIVE_CORRUPT')


def store_bundle(output_root, files):
    """Internal custody writer: stage then rename; existing directories are verified, never repaired."""
    require(type(files) is dict and 1 <= len(files) <= 16 and 'file_index.json' not in files, 'H38_BUNDLE')
    for name, raw in files.items():
        _component(name)
        require(type(raw) is bytes and len(raw) <= ARCHIVE_LIMIT, 'H38_BUNDLE_SIZE')
    root = safe_path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    safe_path(root)
    index = _index(files)
    target = root / sha256(index)
    safe_path(target)
    if target.exists():
        _verify_bytes(target, files)
        return target
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    expected = files | {'file_index.json': index}
    try:
        for name, raw in expected.items():
            with (staging/name).open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        try:
            staging.rename(target)
        except OSError:
            if not target.exists():
                raise
            _verify_bytes(target, files)
        _verify_bytes(target, files)
        return target
    finally:
        # Delete only our known staging files, never recursively traverse caller paths.
        if staging.exists():
            safe_path(staging)
            require(staging.parent == root and staging.name.startswith('.staging-'), 'H38_STAGING_PATH')
            for name in expected:
                item = safe_path(staging/name)
                if item.exists():
                    item.unlink()
            staging.rmdir()


def archive_local(output_root, input_root, *, reviews=(), cutoff):
    inputs = _snapshot(input_root)
    result = _inspect(inputs, reviews, cutoff)
    return store_bundle(output_root, _bundle(inputs, result, reviews))


def verify_archive(target, *, reviews=(), cutoff):
    """Recompute from originals and host reviews; stored audit copies cannot grant trust."""
    inputs = _snapshot(target)
    result = _inspect(inputs, reviews, cutoff)
    _verify_bytes(target, _bundle(inputs, result, reviews))
    return result
