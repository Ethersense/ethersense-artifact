"""Summarise the Wi-Fi A/B (HackRF idle vs 20 MS/s capture) from the raw router outputs in raw/.

Usage: python -I analyze_wifi.py <raw_dir> <out_dir>
"""
import json, re, statistics as st, sys
from pathlib import Path

R, O = Path(sys.argv[1]), Path(sys.argv[2]); O.mkdir(parents=True, exist_ok=True)


def j(p):
    d = json.loads(p.read_text(encoding='utf-8'))
    if 'error' in d:
        return {'error': d['error']}
    e = d['end']
    if 'sum_received' in e:  # TCP
        out = dict(mbps_rx=e['sum_received']['bits_per_second'] / 1e6, mbps_tx=e['sum_sent']['bits_per_second'] / 1e6,
                   retrans=e['sum_sent'].get('retransmits'))
    else:  # UDP
        s = e['sum']; out = dict(mbps=s['bits_per_second'] / 1e6, jitter_ms=s['jitter_ms'], lost_pct=s['lost_percent'])
    out['cpu_host_total'] = e.get('cpu_utilization_percent', {}).get('host_total')
    return out


def cpu_busy(t):
    a = [int(x) for x in (R / f'{t}.cpu0').read_text().split()[1:]]; b = [int(x) for x in (R / f'{t}.cpu1').read_text().split()[1:]]
    d = [y - x for x, y in zip(a, b)]; return 100 * (1 - (d[3] + d[4]) / sum(d))


def hackrf(t):
    p = R / f'{t}.hackrf.txt'
    if not p.exists():
        return None
    s = p.read_text(errors='replace')
    rates = [float(x) for x in re.findall(r'([\d.]+) MiB/second', s)]
    return dict(n_reports=len(rates), mib_s_median=st.median(rates) if rates else None, mib_s_min=min(rates) if rates else None,
                problems=re.findall(r'(?i)(overflow|underflow|dropped|error|couldn)[^\n]*', s)[:5])


def ping(t):
    if not (R / f'{t}.wifi_ping.txt').exists():
        return None  # round 2 has no ping (ICMP blocked by the HUGO firewall in round 1)
    s = (R / f'{t}.wifi_ping.txt').read_text(errors='replace')
    m = re.search(r'min/avg/max = ([\d.]+)/([\d.]+)/([\d.]+)', s); l = re.search(r'(\d+)% packet loss', s)
    return dict(rtt_avg_ms=float(m.group(2)) if m else None, rtt_max_ms=float(m.group(3)) if m else None, loss_pct=int(l.group(1)) if l else None)


rows = []
for rep in (1, 2, 3, 4, 5, 6):
    for cond in ('idle', 'capture'):
        t = f'r{rep}_{cond}'
        if not (R / f'{t}.cpu1').exists():
            continue
        rows.append(dict(trial=t, rep=rep, cond=cond, wifi_tcp_tx=j(R / f'{t}.wifi_tcp_tx.json'), wifi_tcp_rx=j(R / f'{t}.wifi_tcp_rx.json'),
                         wifi_udp50=j(R / f'{t}.wifi_udp50.json'), wired_tcp_tx=j(R / f'{t}.wired_tcp_tx.json'), ping=ping(t),
                         router_cpu_busy_pct=cpu_busy(t), hackrf=hackrf(t), link=(R / f'{t}.link.txt').read_text().split()))
(O / 'wifi_ab_records.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')

metrics = [('Wi-Fi TCP, MT3000 sends (Mbit/s)', lambda r: r['wifi_tcp_tx']['mbps_rx']),
           ('Wi-Fi TCP, MT3000 receives (Mbit/s)', lambda r: r['wifi_tcp_rx']['mbps_rx']),
           ('Wi-Fi TCP retransmissions (MT3000 sends)', lambda r: r['wifi_tcp_tx']['retrans']),
           ('Wi-Fi UDP 50 Mbit/s loss (%)', lambda r: r['wifi_udp50']['lost_pct']),
           ('Wi-Fi UDP jitter (ms)', lambda r: r['wifi_udp50']['jitter_ms']),
           ('Wired TCP control (Mbit/s)', lambda r: r['wired_tcp_tx']['mbps_rx']),
           ('Router CPU busy during trial (%)', lambda r: r['router_cpu_busy_pct'])]
lines = ['| Metric | idle (valid runs) | capture (valid runs) | median capture - idle |', '|---|---|---|---|']
summary = {}
for name, f in metrics:
    def g(r):
        try:
            return f(r)
        except (KeyError, TypeError):
            return None  # iperf3 run failed (error recorded in wifi_ab_records.json)
    v = {c: [x for x in (g(r) for r in rows if r['cond'] == c) if x is not None] for c in ('idle', 'capture')}
    fmt = lambda xs: ', '.join(f'{x:.2f}' if isinstance(x, float) else str(x) for x in xs)
    d = st.median(v['capture']) - st.median(v['idle']) if all(v.values()) else None
    summary[name] = dict(idle=v['idle'], capture=v['capture'], median_diff=d)
    lines.append(f'| {name} | {fmt(v["idle"])} | {fmt(v["capture"])} | {d:+.2f} |' if d is not None else f'| {name} | | | |')
hk = [r['hackrf'] for r in rows if r['cond'] == 'capture']
lines.append(''); lines.append('HackRF during capture trials: ' + '; '.join(
    f"{h['n_reports']} reports, median {h['mib_s_median']:.1f} MiB/s, min {h['mib_s_min']:.1f}, issues {h['problems']}" for h in hk if h))
(O / 'wifi_ab_summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
(O / 'wifi_ab_summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
print('\n'.join(lines))
