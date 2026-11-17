"""Capture durable actual process/exit evidence for both already linked guest lanes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parent
run = root.parents[1]
guest = root / 'Guest/DirectPeGuest-1e9f8bd1'
node = run / 'Toolchain/emsdk/node/24.19.0_64bit/node.exe'
import sys
for lane in [sys.argv[1]]:
    out = guest / lane
    command = [str(node), str(out / 'direct_pe_guest.js')]
    paths = [out / ('direct_pe_guest.' + suffix) for suffix in ['js','wasm','data']]
    snapshot = lambda: {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    before = snapshot()
    receipt = {'lane':lane,'command':command,'working_directory':str(out),
               'node_sha256':hashlib.sha256(node.read_bytes()).hexdigest(),
               'start_utc':datetime.now(timezone.utc).isoformat(),'files_before':before}
    with (out / 'node-proof.log').open('w') as log:
        process = subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT)
        receipt['pid'] = process.pid
        try:
            receipt['exit_code'] = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            receipt['exit_code'] = process.wait()
            receipt['timed_out'] = True
    text = (out / 'node-proof.log').read_text()
    receipt.update(end_utc=datetime.now(timezone.utc).isoformat(), files_after=snapshot(), stdout=text)
    receipt['passed'] = receipt['exit_code'] == 0 and receipt['files_before'] == receipt['files_after'] and all(token in text for token in ['DIRECT_PE_EXCEPTION_DELEGATE hr=0x00000000','DIRECT_PE_MANAGED_EH flagsPositive=31 flagsNegative=31 expected=31','DIRECT_PE_MANAGED_EH_PASS typed=1 newThrowFromCatch=1 rethrow=1 finally=3 filter=1','DIRECT_PE_INITIALIZE hr=0x00000000','DIRECT_PE_CREATE_DELEGATE hr=0x00000000','DIRECT_PE_ROUNDTRIP positive=45 negative=-33 nativeCalls=2','DIRECT_PE_SHUTDOWN hr=0x00000000 latched=0','DIRECT_PE_GUEST_PASS pointer=8'])
    (out / 'node-proof.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'lane':lane,'pid':receipt['pid'],'exit_code':receipt['exit_code'],'passed':receipt['passed']}), flush=True)
    if not receipt['passed']:
        raise SystemExit(1)
