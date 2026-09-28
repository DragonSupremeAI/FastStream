from playwright.sync_api import sync_playwright
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBTITLECAT = ROOT.parent / "SubtitleCatAPI"

with sync_playwright() as p, tempfile.TemporaryDirectory(prefix='faststream-brave-test-') as profile:
    extensions = f'{ROOT / "chrome"},{SUBTITLECAT / "extension"}'
    args=['--no-sandbox', f'--disable-extensions-except={extensions}', f'--load-extension={extensions}']
    def launch():
        return p.chromium.launch_persistent_context(profile, executable_path='/usr/bin/brave-browser', headless=True, args=args)
    c=launch()
    page=c.new_page(); page.goto('brave://flags/#file-system-access-api')
    page.locator('flags-experiment#file-system-access-api select').select_option(index=1)
    c.close(); c=launch()
    page=c.new_page(); page.wait_for_timeout(700)
    sw=next(w for w in c.service_workers if '/background/' in w.url)
    base=sw.url.rsplit('/background/',1)[0]
    catbase=next(w for w in c.service_workers if '/service-worker.js' in w.url).url.rsplit('/',1)[0]
    page.goto(base+'/player/options/subtitle-folder.html')
    assert page.evaluate('typeof showDirectoryPicker') == 'function'
    page.wait_for_timeout(800); assert page.evaluate("document.getElementById('status').textContent === 'No folder selected.'")
    # A real serializable directory handle, with fixture files in isolated OPFS.
    page.evaluate('''async () => {
      const {LocalSubtitleFolder} = await import('../ui/subtitles/LocalSubtitleFolder.mjs');
      const root = await navigator.storage.getDirectory();
      const dir = await root.getDirectoryHandle('SRT', {create:true});
      for (const name of ['SSIS.324-en.srt', 'SSIS-324-fr.srt', 'SSIS-3245-en.srt']) {
        const file = await dir.getFileHandle(name, {create:true});
        const writer = await file.createWritable();
        await writer.write('1\\n00:00:01,000 --> 00:00:03,000\\nHello '+name+'\\n');
        await writer.close();
      }
      await new LocalSubtitleFolder().saveHandle(dir);
    }''')
    c.close(); c=launch()
    page=c.new_page(); page.goto(base+'/player/options/subtitle-folder.html')
    page.wait_for_timeout(800); assert page.evaluate("document.getElementById('status').textContent.startsWith('Connected')")
    scan=page.evaluate("chrome.runtime.sendMessage({type:'LOCAL_SUBTITLE_SCAN',code:'SSIS-324'})")
    assert len(scan['files']) == 2, scan
    print('PASS: saved handle survives full Brave restart; background scan excludes different codes')
    page.goto(base+'/player/index.html')
    page.wait_for_timeout(800); assert page.evaluate('window.fastStream && window.fastStream.interfaceController.subtitlesManager')
    state=page.evaluate('''async () => {
      const manager = window.fastStream.interfaceController.subtitlesManager;
      window.fastStream.options.autoEnableBestSubtitles = true;
      manager.settingsManager.getSettings().defaultLanguage = 'en';
      window.fastStream.setMediaInfo({name:'unusable cleaned name',originalTitle:'Watch SSIS 324'});
      await manager.loadMatchingLocalSubtitles();
      await manager.loadMatchingLocalSubtitles();
      return {tracks:manager.tracks.map(t=>t.label),active:manager.activeTracks.map(t=>t.language)};
    }''')
    assert len(state['tracks']) == 2, state
    assert state['active'] == ['en'], state
    print('PASS: SRT parsing, original-title matching, deduplication and preferred-language activation')
    state=page.evaluate('''async () => {
      const manager = window.fastStream.interfaceController.subtitlesManager;
      window.fastStream.setMediaInfo({originalTitle:'Another video ABC-555'});
      await manager.loadMatchingLocalSubtitles();
      return {tracks:manager.tracks.length,active:manager.activeTracks.length};
    }''')
    assert state == {'tracks':0,'active':0}, state
    print('PASS: changing the video removes previous local tracks')
    page.route('https://faststream-fixture.test/**', lambda route: route.fulfill(content_type='text/html', body=f'<title>SSIS 324 fixture</title><iframe src="{base}/player/index.html" width="900" height="600"></iframe>'))
    page.goto('https://faststream-fixture.test/video')
    page.wait_for_timeout(1200)
    frame=next(f for f in page.frames if f.url.startswith(base+'/player/index.html'))
    state=frame.evaluate("({title:window.fastStream.mediaInfo.originalTitle, tracks:window.fastStream.interfaceController.subtitlesManager.tracks.map(t=>t.label)})")
    assert state['title'] == 'SSIS 324 fixture', state
    assert len(state['tracks']) == 2, state
    page.evaluate("document.title='ABC-555 different video'");page.wait_for_timeout(800)
    assert frame.evaluate('window.fastStream.interfaceController.subtitlesManager.tracks.length') == 0
    print('PASS: embedded player receives original page title, shares folder access, and responds to title changes')
    page.goto(catbase+'/sidepanel.html')
    page.wait_for_timeout(800); assert page.evaluate("document.getElementById('download-folder-input').value === 'SRT'")
    assert not page.locator('#ask-download-location-chk').is_checked()
    page.locator('#download-folder-input').fill('SRT/English');page.locator('#download-folder-input').dispatch_event('change')
    page.reload(); page.wait_for_timeout(800); assert page.evaluate("document.getElementById('download-folder-input').value === 'SRT/English'")
    print('PASS: SubtitleCat loads module scripts, defaults to automatic SRT saving, persists changed subfolder')
    page.route('https://www.subtitlecat.com/index.php?*', lambda route: route.fulfill(content_type='text/html', body='<table class="sub-table"><tbody><tr><td><a href="fixture.html">SSIS 324 Fixture</a></td><td></td><td>100</td><td>2</td><td>1</td></tr></tbody></table>'))
    page.route('https://www.subtitlecat.com/fixture.html', lambda route: route.fulfill(content_type='text/html', body='<div class="sub-single"><img class="flag" alt="en"><span>English</span><a class="green-link" href="/fixture-en.srt">Download</a></div>'))
    page.evaluate("chrome.downloads.download = async options => { window.testDownload = options; return 1; }")
    page.locator('#search-input').fill('SSIS-324');page.locator('#search-btn').click()
    page.locator('.results-item').first.click();page.locator('#download-action-btn').click();page.wait_for_timeout(300)
    options=page.evaluate('window.testDownload')
    assert options['filename'].startswith('SRT/English/SSIS-324.'), options
    assert options['filename'].endswith('-en.srt'), options
    assert options['saveAs'] is False, options
    print('PASS: SubtitleCat download action sends a canonical filename and saveAs=false to Brave')
    c.close()
