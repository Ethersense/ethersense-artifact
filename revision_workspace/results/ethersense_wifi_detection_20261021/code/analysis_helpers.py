"""Pure analysis helpers extracted unchanged from the historical manage.py.
Host login, transfer and launch code is not included.
"""
import hashlib
import re
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()

def verify(directory):
    manifest=directory/'SHA256SUMS'
    records={}
    for line in manifest.read_text(encoding='ascii').splitlines():
        match=re.fullmatch(r'([a-f0-9]{64})\s+\./([A-Za-z0-9_.]+)',line)
        if not match:
            raise ValueError('Invalid manifest entry')
        name=match.group(2)
        if sha(directory/name)!=match.group(1):
            raise ValueError('Checksum mismatch: '+str(directory/name))
        records[name]=match.group(1)
    return records

def make_psd(path):
    import numpy as np
    from scipy.fft import fft,fftshift
    from scipy.signal.windows import hann
    fs=20_000_000;nfft=65536;hop=nfft//2
    raw=np.memmap(path,dtype=np.int8,mode='r').reshape(-1,2)
    window=hann(nfft,sym=False).astype(np.float32)
    starts=np.arange(0,len(raw)-nfft+1,hop)
    accumulated=np.zeros(nfft,dtype=np.float64)
    for begin in range(0,len(starts),32):
        group=starts[begin:begin+32]
        data=np.stack([raw[s:s+nfft,0].astype(np.float32)+1j*raw[s:s+nfft,1].astype(np.float32) for s in group])/128.0
        data-=data.mean(axis=1,keepdims=True)
        transformed=fft(data*window,axis=1,workers=4)
        accumulated+=(np.abs(transformed)**2).sum(axis=0,dtype=np.float64)
    psd=fftshift(accumulated/len(starts)/(fs*(window.astype(np.float64)**2).sum()))
    frequency=fftshift(np.fft.fftfreq(nfft,1/fs))
    return frequency,psd,{'windows':len(starts),'nfft':nfft,'hop':hop,'window':'periodic Hann',
                         'normalization':'int8/128, two-sided density per Hz, per-window mean removed'}
