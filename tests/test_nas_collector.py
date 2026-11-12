import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nas/app'))
import canon_collector as collector


class ProtocolSelectionTests(unittest.TestCase):
    def test_chmp_only_never_initializes_cpca_after_timeouts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector.protocol, 'query', side_effect=TimeoutError('offline')):
                with patch.object(collector.protocol, 'CPCAClient') as cpca:
                    result = collector.collect_one('192.0.2.10', Path(directory), 1, 0,
                                                   chmp_only=True)
        cpca.assert_not_called()
        self.assertEqual(result['status'], 'not_confirmed')
        self.assertEqual(len(result['errors']), 3)

    def test_auto_falls_back_to_cpca_and_preserves_raw_status(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(collector.protocol, 'query', side_effect=TimeoutError('no CHMP')):
                with patch.object(collector.protocol, 'CPCAClient') as cpca:
                    client = cpca.return_value.__enter__.return_value
                    client.initialize.return_value = 'iPF785'
                    client.read_status.return_value = b'Status report\r\n'
                    result = collector.collect_one('192.0.2.20', folder, 1, 0,
                                                   cpca_models=('iPF785',))
            client.initialize.assert_called_once_with(allowed_models=('iPF785',))
            self.assertEqual(result['protocol'], 'CPCA')
            self.assertEqual(result['status'], 'collected')
            self.assertEqual((folder / '192.0.2.20/status.bin').read_bytes(), b'Status report\r\n')

    def test_chmp_success_writes_xml_and_skips_cpca(self):
        def response(**fields):
            body = ''.join(f'<ivec:{key}>{value}</ivec:{key}>' for key, value in fields.items())
            return ('<root xmlns:ivec="http://www.canon.com/ns/cmd/2008/07/common/">'
                    + body + '</root>').encode()

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            device = response(response='OK', manufacturer='Canon', model='TX-3000',
                              product_serialnumber='SYNTHETIC')
            counter = response(response='OK')
            with patch.object(collector.protocol, 'query', side_effect=[device, counter]):
                with patch.object(collector.protocol, 'CPCAClient') as cpca:
                    result = collector.collect_one('192.0.2.10', folder, 1, 0)
            cpca.assert_not_called()
            self.assertEqual(result['status'], 'collected')
            self.assertEqual((folder / '192.0.2.10/device_1.3.0.xml').read_bytes(), device)
            self.assertTrue((folder / '192.0.2.10/result.json').is_file())


if __name__ == '__main__':
    unittest.main()
