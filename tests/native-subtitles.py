import base64
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

HOST = Path(__file__).resolve().parents[1] / 'native/host.py'
spec = importlib.util.spec_from_file_location('subtitle_host', HOST)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class NativeSubtitlesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'SRT'
        self.folder.mkdir()
        host.CONFIG_FILE = self.root / 'settings.json'
        host.dispatch({'action': 'configure', 'path': str(self.folder)})

    def tearDown(self):
        self.temp.cleanup()

    def test_screenshot_codes_and_suffixed_file_reads(self):
        examples = json.loads(Path(__file__).with_name('subtitle-code-cases.json').read_text())
        for filename, expected in examples:
            with self.subTest(filename=filename):
                self.assertEqual(host.detect_code(filename), expected)
        (self.folder / 'NHDTB-913uc-en.srt').write_text('suffixed subtitle')
        (self.folder / 'NHDTB-9130uc-en.srt').write_text('different code')
        files = host.dispatch({'action': 'scan', 'code': 'NHDTB-913'})['files']
        self.assertEqual([file['name'] for file in files], ['NHDTB-913uc-en.srt'])
        result = host.dispatch({'action': 'read', 'code': 'NHDTB-913', 'name': files[0]['name'], 'version': files[0]['version']})
        self.assertEqual(base64.b64decode(result['data']), b'suffixed subtitle')

    def test_configuration_survives_module_reload(self):
        another_spec = importlib.util.spec_from_file_location('fresh_host', HOST)
        fresh = importlib.util.module_from_spec(another_spec)
        another_spec.loader.exec_module(fresh)
        fresh.CONFIG_FILE = host.CONFIG_FILE
        self.assertEqual(fresh.dispatch({'action': 'status'})['path'], str(self.folder))

    def test_matching_excludes_symlinks_other_codes_and_non_srt(self):
        (self.folder / 'SSIS.324-en.srt').write_text('subtitle')
        (self.folder / 'SSIS-3245-en.srt').write_text('different video')
        (self.folder / 'SSIS-324.txt').write_text('not srt')
        outside = self.root / 'secret.srt'
        outside.write_text('outside')
        (self.folder / 'SSIS-324-fr.srt').symlink_to(outside)
        result = host.dispatch({'action': 'scan', 'code': 'SSIS-324'})
        self.assertEqual([f['name'] for f in result['files']], ['SSIS.324-en.srt'])
        for name in ['../secret.srt', str(outside), 'SSIS-324-fr.srt', 'SSIS-3245-en.srt']:
            with self.assertRaises((ValueError, OSError)):
                host.dispatch({'action': 'read', 'code': 'SSIS-324', 'name': name, 'version': ''})

    def test_large_unicode_subtitle_reads_in_native_protocol_sized_chunks(self):
        content = ('字幕 café\n' * 60000).encode()
        (self.folder / 'SSIS-324-en.srt').write_bytes(content)
        file = host.dispatch({'action': 'scan', 'code': 'SSIS-324'})['files'][0]
        offset, assembled = 0, bytearray()
        while True:
            result = host.dispatch({'action': 'read', 'code': 'SSIS-324', 'name': file['name'], 'version': file['version'], 'offset': offset})
            self.assertLess(len(json.dumps(result).encode()), 1024 * 1024)
            assembled.extend(base64.b64decode(result['data']))
            if result['done']:
                break
            offset = result['nextOffset']
        self.assertEqual(assembled, content)
        (self.folder / file['name']).write_text('changed')
        with self.assertRaises(ValueError):
            host.dispatch({'action': 'read', 'code': 'SSIS-324', 'name': file['name'], 'version': file['version']})

    def test_forget_and_missing_folder(self):
        self.folder.rmdir()
        with self.assertRaises(ValueError):
            host.dispatch({'action': 'status'})
        host.dispatch({'action': 'forget'})
        self.assertEqual(host.dispatch({'action': 'status'}), {'status': 'unconfigured'})

    def test_stdio_message_framing_and_error_response(self):
        payload = json.dumps({'action': 'unknown'}).encode()
        result = subprocess.run([sys.executable, str(HOST)], input=struct.pack('=I', len(payload)) + payload, capture_output=True, check=True)
        length = struct.unpack('=I', result.stdout[:4])[0]
        self.assertEqual(length, len(result.stdout) - 4)
        self.assertEqual(json.loads(result.stdout[4:])['status'], 'error')


if __name__ == '__main__':
    unittest.main()
