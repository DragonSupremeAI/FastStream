#!/usr/bin/env python3
"""Install the FastStream subtitle helper for Brave on Linux (no root required)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

HOST = 'org.faststream.subtitles'


def unpacked_id(path):
    # Chromium derives an unpacked extension's ID from its absolute load path.
    digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:32]
    return ''.join(chr(ord('a') + int(character, 16)) for character in digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension-id', action='append', help='FastStream ID from brave://extensions; repeat for multiple installations')
    parser.add_argument('--browser-dir', type=Path, help='Brave native-host base directory (defaults to its standard config location)')
    parser.add_argument('--install-dir', type=Path, help='Override helper installation directory')
    parser.add_argument('--folder', type=Path, help='Optionally configure an existing subtitle folder')
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('This installer currently supports Linux Brave.')
    ids = args.extension_id or [unpacked_id(Path(__file__).resolve().parents[1] / 'chrome')]
    if any(not re.fullmatch('[a-p]{32}', value) for value in ids):
        parser.error('Extension IDs must contain 32 letters from a to p.')
    config_root = Path(os.environ.get('CHROME_CONFIG_HOME') or os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    data_root = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    install_dir = (args.install_dir or data_root / 'faststream-subtitles').expanduser().resolve()
    browser_dir = (args.browser_dir or config_root / 'BraveSoftware/Brave-Browser').expanduser().resolve()
    folder = args.folder.expanduser().resolve(strict=True) if args.folder else None
    if folder and not folder.is_dir():
        parser.error('--folder must be a directory')
    install_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    script = install_dir / 'host.py'
    shutil.copyfile(Path(__file__).with_name('host.py'), script)
    script.chmod(0o700)
    launcher = install_dir / 'launch.sh'
    # Quote paths as shell code, including installations under paths containing spaces.
    import shlex
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(script)) + ' "$@"\n')
    launcher.chmod(0o700)
    if folder:
        import importlib.util
        spec = importlib.util.spec_from_file_location('installed_subtitle_host', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.dispatch({'action': 'configure', 'path': str(folder)})
    manifest_dir = browser_dir / 'NativeMessagingHosts'
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / f'{HOST}.json'
    # Preserve registrations for other explicitly installed FastStream IDs.
    existing = json.loads(manifest.read_text()).get('allowed_origins', []) if manifest.exists() else []
    origins = sorted(set(existing + [f'chrome-extension://{value}/' for value in ids]))
    manifest.write_text(json.dumps({'name': HOST, 'description': 'FastStream read-only local SRT folder access',
                                    'path': str(launcher), 'type': 'stdio', 'allowed_origins': origins}, indent=2) + '\n')
    print(f'Installed helper: {script}\nRegistered with Brave: {manifest}')
    print('Allowed FastStream IDs: ' + ', '.join(ids))
    print('Reload FastStream, open Local subtitle folder settings, then click Save and connect.')


if __name__ == '__main__':
    main()
