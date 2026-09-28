# Local subtitles in Brave

The subtitle parser and track menu are reused. The background worker scans the
folder and sends matching SRT contents to embedded players. Both FastStream and
SubtitleCat normalize video codes consistently.

## Recommended setup: persistent local helper (Linux)

The helper avoids Brave's expiring filesystem-picker grants. It uses native
messaging over stdin/stdout, has no network listener, and runs only when Brave
requests it. No File System Access API flag is needed.

1. Load/reload FastStream from `chrome/` and SubtitleCat from its `extension/`
   directory in `brave://extensions`. FastStream now requires `nativeMessaging`.
2. Create your shared subtitle directory, for example `~/Downloads/SRT`.
3. From this checkout, install the helper once:

   ```sh
   python3 native/install.py --folder "$HOME/Downloads/SRT"
   ```

   The default extension ID is derived from this checkout's `chrome/` path.
   For a differently installed FastStream, use the exact command shown under
   **First-time helper installation** in its **Local subtitle folder settings**.
   It passes `--extension-id` explicitly. Only registered extension IDs can
   communicate with the helper. A Web Store FastStream version without these
   changes cannot use it.
4. Open FastStream's **Local subtitle folder settings** from the subtitle menu
   or extension options. Click **Save and connect**. Leave the path empty to
   use the installer's saved folder, or enter an absolute path to change it.
5. In SubtitleCat, set the download folder to `SRT` and disable **Ask where to
   save each SRT**. This uses `SRT` inside Brave's configured Downloads location.
   Ensure that location matches FastStream's folder. A conventional absolute
   Downloads path is only an alias for a download subfolder.
6. Open a video whose tab title contains a code such as `SSIS-324`. Matching
   SRTs appear in its subtitle menu automatically, including after restarts.
   Automatic *activation* follows FastStream's existing automatic-subtitle
   setting and preferred language; adding tracks does not force activation.

The helper is installed under `~/.local/share/faststream-subtitles/`, with its
folder setting in `settings.json`. Brave's registration is normally under
`~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts/`.
The installer honors XDG directory overrides (and CHROME_CONFIG_HOME for
Brave's configuration). No root access or Python dependencies are required.
Run the installer again to update it. The installer preserves the folder unless
`--folder` is supplied. To uninstall, remove the
`org.faststream.subtitles.json` registration and the helper installation directory.

Brave looks for native hosts under its **default configuration directory**, even
when launched with a separate `--user-data-dir`. Tests isolate XDG_CONFIG_HOME
as well as the browser profile so they do not modify the user's registration.

## Browser-only alternative

Expand **Browser-only alternative** in the settings tab, enable
**File System Access API** at `brave://flags/#file-system-access-api`, relaunch
Brave, and choose your SRT directory there.

In Brave 150.1.92.141, a real filesystem handle survived restart but its read
permission returned to `prompt`. **Restore folder access** renews that grant
without choosing the directory again. This alternative cannot guarantee
unattended access across restarts. The native helper is the recommended method.

## Matching, updates and access boundaries

- IDs use 2–5 letters and exactly 3 digits (including leading zeros). Attached
  letter suffixes such as `uc` are ignored, so `NHDTB-913uc-en.srt` matches
  `NHDTB-913`. Two-letter prefixes cover filenames such as `AP-334-en.srt`. Hyphens, spaces, dots and underscores are
  accepted separators; IDs match exactly. General movie-title matching is not
  implemented. The JavaScript normalizers in both repositories and the helper's
  Python normalizer should be updated together.
- FastStream preserves the original tab title before movie-search cleanup.
- Only SRTs immediately inside the configured folder are scanned. Native mode
  rejects symbolic links and non-regular files. There is no arbitrary file-read
  endpoint: each read must have the exact matching video code and a basename.
- Scans run when metadata or folder settings change, on player focus/visibility,
  and via **Check subtitle folder now**. There is no continuous filesystem watcher.
- Duplicate tracks are avoided. Changing the video code or folder setting clears
  previously loaded local tracks before rescanning.
- Each file is limited to 8 MiB and each scan to 24 MiB. Native mode examines at
  most 128 matching entries and sends file contents in 192 KiB binary chunks
  encoded as base64, below Chromium's 1 MiB native-response limit.
- File size/inode/modification metadata is checked during native reads to avoid
  mixing contents if a file changes during a scan. Errors in one file do not
  block other files. Folder access errors appear in the subtitle menu.
- Only extension pages can request scans through the background worker; webpage
  content scripts cannot request subtitle contents. Native configuration writes
  affect the helper's settings only; subtitle files are read-only.

## Validation

```sh
node --test tests/local-subtitles.test.mjs
python3 tests/native-subtitles.py
python3 tests/brave-native-subtitles.py
python3 tests/brave-subtitles.py
```

In SubtitleCat: `node --test tests/downloads.test.mjs`.

Browser tests require Python Playwright and `/usr/bin/brave-browser`; the combined
browser test also needs a sibling SubtitleCatAPI checkout. They use disposable
profiles and fixture files. Native integration verifies real filesystem reads,
full browser restart, and automatic discovery of new files in an embedded player
without enabling the File System Access API. The other suite uses an OPFS fixture
handle for browser-only mode and covers title propagation, parsing, deduplication,
language selection, video changes, settings persistence and SubtitleCat's download
request. OPFS permission persistence does not imply real-folder grant persistence.
