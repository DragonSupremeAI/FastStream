#!/usr/bin/env python3
"""Read-only SRT access over Chromium's native messaging stdio protocol."""
import base64
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import unicodedata

MAX_FILE_SIZE = 8 * 1024 * 1024
CHUNK_SIZE = 192 * 1024
MAX_MATCHES = 128
CONFIG_FILE = Path(__file__).resolve().parent / 'settings.json'
CODE_PATTERN = re.compile(r'(?:^|[^a-z0-9])([a-z]{2,5})[-\s._]*([0-9]{3})[a-z]*(?=$|[^a-z0-9])', re.I | re.ASCII)


def detect_code(value):
    match = CODE_PATTERN.search(unicodedata.normalize('NFKC', str(value or '')))
    return f'{match[1]}-{match[2]}'.upper() if match else None


def read_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def save_config(config):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=CONFIG_FILE.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(config, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CONFIG_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def folder_state():
    folder = read_config().get('folder')
    if not folder:
        return {'status': 'unconfigured'}
    path = Path(folder)
    if not path.is_dir():
        raise ValueError('The saved subtitle folder is unavailable. Check its location in folder settings.')
    return {'status': 'ready', 'name': path.name, 'path': str(path)}


def file_version(info):
    return f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}'


def dispatch(message):
    if not isinstance(message, dict):
        raise ValueError('Expected an object.')
    action = message.get('action')
    if action == 'configure':
        value = message.get('path')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Enter an absolute subtitle folder path.')
        path = Path(value.strip()).expanduser()
        if not path.is_absolute():
            raise ValueError('Enter an absolute subtitle folder path.')
        path = path.resolve(strict=True)
        if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
            raise ValueError('The subtitle folder must exist and be readable.')
        save_config({'folder': str(path)})
        return folder_state()
    if action == 'forget':
        save_config({})
        return {'status': 'unconfigured'}
    if action not in ('status', 'scan', 'read'):
        raise ValueError('Unknown subtitle action.')
    state = folder_state()
    if action == 'status' or state['status'] != 'ready':
        return state
    code = message.get('code')
    if not isinstance(code, str) or detect_code(code) != code:
        raise ValueError('A complete normalized video code is required.')
    folder = Path(state['path'])
    if action == 'scan':
        files, errors = [], []
        examined = 0
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.name.lower().endswith('.srt') or detect_code(entry.name) != code:
                    continue
                examined += 1
                if examined > MAX_MATCHES:
                    errors.append('Match limit reached; only the first 128 files will be loaded.')
                    break
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if info.st_size > MAX_FILE_SIZE:
                        raise ValueError('Subtitle exceeds 8 MiB.')
                    files.append({'name': entry.name, 'size': info.st_size, 'version': file_version(info)})
                except (OSError, ValueError) as error:
                    errors.append(f'{entry.name}: {error}')
        return {**state, 'files': sorted(files, key=lambda item: item['name']), 'errors': errors}
    name = message.get('name')
    if (not isinstance(name, str) or '/' in name or '\\' in name or '\x00' in name
            or not name.lower().endswith('.srt') or detect_code(name) != code):
        raise ValueError('Only matching SRT filenames in the configured folder may be read.')
    offset = message.get('offset', 0)
    if type(offset) is not int or offset < 0 or offset > MAX_FILE_SIZE:
        raise ValueError('Invalid subtitle offset.')
    directory_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # Refuse symlinks and non-regular files, including files replaced after scanning.
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_SIZE:
            raise ValueError('Not a supported subtitle file.')
        if file_version(info) != message.get('version'):
            raise ValueError('Subtitle changed during reading. Scan the folder again.')
        if offset > info.st_size:
            raise ValueError('Invalid subtitle offset.')
        stream.seek(offset)
        data = stream.read(CHUNK_SIZE)
        if file_version(os.fstat(stream.fileno())) != message.get('version'):
            raise ValueError('Subtitle changed during reading. Scan the folder again.')
    return {'status': 'ready', 'data': base64.b64encode(data).decode('ascii'), 'nextOffset': offset + len(data), 'done': offset + len(data) >= info.st_size}


def read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        part = stream.read(length - len(data))
        if not part:
            if not data:
                return None
            raise ValueError('Truncated native message.')
        data.extend(part)
    return bytes(data)


def main():
    while True:
        header = read_exact(sys.stdin.buffer, 4)
        if header is None:
            return
        length = struct.unpack('=I', header)[0]
        if length > 64 * 1024:
            return
        try:
            payload = read_exact(sys.stdin.buffer, length)
            result = dispatch(json.loads(payload))
        except (ValueError, TypeError, OSError) as error:
            result = {'status': 'error', 'message': str(error)}
        encoded = json.dumps(result, ensure_ascii=False).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('=I', len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
