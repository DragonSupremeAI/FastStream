from playwright.sync_api import sync_playwright
from pathlib import Path
import subprocess, tempfile, sys, os
env=dict(os.environ)
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p, tempfile.TemporaryDirectory(prefix='faststream-native-test-') as temp:
 root=Path(temp); profile=root/'profile'; helper=root/'helper'; folder=root/'SRT'; folder.mkdir()
 env['XDG_CONFIG_HOME']=str(root/'config'); env.pop('CHROME_CONFIG_HOME',None)
 browser_dir=root/'config/BraveSoftware/Brave-Browser'
 (folder/'SSIS-324uc-en.srt').write_text('1\n00:00:01,000 --> 00:00:03,000\nHello from helper\n')
 args=['--no-sandbox',f'--disable-extensions-except={ROOT}/chrome',f'--load-extension={ROOT}/chrome']
 c=p.chromium.launch_persistent_context(str(profile),executable_path='/usr/bin/brave-browser',headless=True,args=args,env=env)
 sw=c.service_workers[0] if c.service_workers else c.wait_for_event('serviceworker'); base=sw.url.rsplit('/background/',1)[0]; extid=base.split('://')[1]
 subprocess.run([sys.executable,str(ROOT/'native/install.py'),'--extension-id',extid,'--browser-dir',str(browser_dir),'--install-dir',str(helper),'--folder',str(folder)],check=True)
 page=c.new_page();page.goto(base+'/player/options/subtitle-folder.html');page.wait_for_timeout(500)
 page.locator('#connect-native').click();page.wait_for_timeout(1200)
 print('status',page.locator('#status').inner_text(),flush=True)
 print('permissions',page.evaluate("chrome.permissions.contains({permissions:['nativeMessaging']})"),flush=True)
 assert page.evaluate("chrome.permissions.contains({permissions:['nativeMessaging']})")
 scan=page.evaluate("chrome.runtime.sendMessage({type:'LOCAL_SUBTITLE_SCAN',code:'SSIS-324'})")
 assert len(scan['files']) == 1, scan
 assert 'Hello from helper' in scan['files'][0]['text']
 print('PASS: native messaging reads a real filesystem SRT without the File System Access flag',flush=True)
 c.close()
 c=p.chromium.launch_persistent_context(str(profile),executable_path='/usr/bin/brave-browser',headless=True,args=args,env=env)
 page=c.new_page();page.goto(base+'/player/options/subtitle-folder.html');page.wait_for_timeout(700)
 assert 'through the local helper' in page.locator('#status').inner_text(), page.locator('#status').inner_text()
 assert page.evaluate('typeof showDirectoryPicker') == 'undefined'
 scan=page.evaluate("chrome.runtime.sendMessage({type:'LOCAL_SUBTITLE_SCAN',code:'SSIS-324'})")
 assert len(scan['files']) == 1, scan
 print('PASS: permission, folder selection and actual file access survive a full Brave restart',flush=True)
 (folder/'SSIS.324-fr.srt').write_text('1\n00:00:01,000 --> 00:00:03,000\nNew subtitle after restart\n')
 page.route('https://faststream-fixture.test/**',lambda route: route.fulfill(content_type='text/html',body=f'<title>SSIS 324</title><iframe src="{base}/player/index.html"></iframe>'))
 page.goto('https://faststream-fixture.test/video');page.wait_for_timeout(1500)
 frame=next(f for f in page.frames if f.url.startswith(base+'/player/index.html'))
 tracks=frame.evaluate('window.fastStream.interfaceController.subtitlesManager.tracks.map(t=>t.label)')
 assert len(tracks)==2, tracks
 print('PASS: new SRTs are discovered automatically by an embedded player after restart',flush=True)
 c.close()
