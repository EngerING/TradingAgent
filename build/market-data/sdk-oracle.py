"""Install no SDK client: extract its Python sources into an ignored CI-only directory."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

root = Path('tmp/m03a-ci')
root.mkdir(parents=True,exist_ok=True)
archive = root/'twsapi.zip'
with urllib.request.urlopen('https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip',timeout=60) as response:
    payload = response.read(16777217)
assert len(payload) <= 16777216, 'SDK_ARCHIVE_LIMIT'
assert hashlib.sha256(payload).hexdigest() == '673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3', 'SDK_DIGEST'
archive.write_bytes(payload)
with zipfile.ZipFile(archive) as source:
    for member in source.infolist():
        prefix = 'IBJts/source/pythonclient/ibapi/'
        if not member.filename.startswith(prefix) or member.is_dir(): continue
        relative = Path('ibapi')/member.filename[len(prefix):]
        assert '..' not in relative.parts and not relative.is_absolute(), 'SDK_MEMBER_PATH'
        assert member.file_size <= 2097152, 'SDK_MEMBER_SIZE'
        destination = root/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(source.read(member))
print('SDK_10_50_2_OFFLINE_ORACLE_VERIFIED')
