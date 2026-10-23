"""Default entrypoint is inert; approval input never becomes broker authority by itself."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_agent.market_data.__main__ import main


class EntrypointTests(unittest.TestCase):
    def test_default_no_socket_no_storage(self):
        output = io.StringIO()
        with patch('socket.socket',side_effect=AssertionError('fixture')),contextlib.redirect_stdout(output):
            self.assertEqual(0,main([]))
        value = json.loads(output.getvalue())
        self.assertEqual('DISABLED',value['code'])
        self.assertEqual('NO_TRADE',value['decision'])
        self.assertFalse(value['execution_authorized'])

    def test_missing_external_approval_is_closed_redacted(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(output):
            self.assertEqual(1,main(['--approved-data-only','--approval-directory',directory,
                                     '--archive-directory',str(Path(directory)/'archive')]))
            self.assertFalse((Path(directory)/'archive').exists())
        self.assertEqual('LOCAL_APPROVAL_OR_STORAGE_REJECTED',json.loads(output.getvalue())['code'])


if __name__ == '__main__': unittest.main()
