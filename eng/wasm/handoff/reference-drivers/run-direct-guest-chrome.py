"""Use the existing task-local BrowserHarness for the actual linked CLR guest."""
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
out = root / 'Guest/DirectPeGuest-1e9f8bd1/Native64'
receipt = json.loads((out / 'build-receipt.json').read_text())
if not receipt['passed']:
    raise RuntimeError('Actual successful normal CMake build required')
(out / 'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Direct PE CLR guest</title><link rel="icon" href="data:,">
<script>var Module = {onAbort: reason => console.error('DIRECT_PE_ABORT ' + reason),
onExit: status => { window.probeExit = status; console.log('DIRECT_PE_BROWSER_EXIT ' + status); }};</script>
<script src="direct_pe_guest.js"></script>''')
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()
    def log_message(self, *args):
        pass
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(out)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
result = {'scope':'Actual linked interpreter-only JS-EH native64 CoreCLR direct PE guest in Chrome, not UE or UnrealSharp gameplay.',
          'browser_harness':'UE/BrowserHarness existing task-local Playwright environment',
          'executable':'C:/Program Files/Google/Chrome/Application/chrome.exe',
          'launch_args':['--enable-unsafe-webgpu','--enable-features=SharedArrayBuffer','--headless=new'],
          'http_headers':{'Cross-Origin-Opener-Policy':'same-origin','Cross-Origin-Embedder-Policy':'require-corp'},
          'console':[], 'page_errors':[]}
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=result['executable'], headless=True, args=result['launch_args'])
        try:
            result['browser_version'] = browser.version
            page = browser.new_page()
            page.on('console', lambda event: result['console'].append({'type':event.type,'text':event.text}))
            page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='load')
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if result['page_errors'] or page.evaluate('window.probeExit !== undefined'):
                    break
                page.wait_for_timeout(100)
            result['environment'] = page.evaluate('({crossOriginIsolated,sharedArrayBuffer:typeof SharedArrayBuffer === "function",exitCode:window.probeExit ?? null})')
        finally:
            browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
result['console_errors'] = [row['text'] for row in result['console'] if row['type'] == 'error']
text = '\n'.join(row['text'] for row in result['console'])
result['files'] = {name:sha256((out / name).read_bytes()).hexdigest() for name in ['direct_pe_guest.js','direct_pe_guest.wasm','direct_pe_guest.data','index.html']}
result['passed'] = not result['page_errors'] and not result['console_errors'] and result['environment']['crossOriginIsolated'] and result['environment']['exitCode'] == 0 and all(token in text for token in ['DIRECT_PE_EXCEPTION_DELEGATE hr=0x00000000','DIRECT_PE_MANAGED_EH flagsPositive=31 flagsNegative=31 expected=31','DIRECT_PE_MANAGED_EH_PASS typed=1 newThrowFromCatch=1 rethrow=1 finally=3 filter=1','DIRECT_PE_INITIALIZE hr=0x00000000','DIRECT_PE_CREATE_DELEGATE hr=0x00000000','DIRECT_PE_ROUNDTRIP positive=45 negative=-33 nativeCalls=2','DIRECT_PE_SHUTDOWN hr=0x00000000 latched=0','DIRECT_PE_GUEST_PASS pointer=8'])
(out / 'chrome-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['passed'] else 1)
