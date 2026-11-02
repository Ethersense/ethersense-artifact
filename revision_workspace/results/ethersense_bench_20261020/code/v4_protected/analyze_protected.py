"""Verify and summarize real, completed short Wi-Fi trials; keep cohorts separate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics as stats


def text(path):
    return path.read_text(encoding="utf-8-sig")


def verify(trial):
    manifest = trial / "SHA256SUMS"
    if not manifest.exists():
        return False, "missing_manifest", 0
    count = 0
    for line in text(manifest).splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})\s+\./([A-Za-z0-9_.]+)", line)
        if not match or match[2] in {".", ".."}:
            return False, "invalid_manifest_entry", count
        path = trial / match[2]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != match[1]:
            return False, "checksum_mismatch:" + match[2], count
        count += 1
    return True, "verified", count


def cpu(trial):
    before = [int(v) for v in text(trial / "cpu_before.txt").split()[1:9]]
    after = [int(v) for v in text(trial / "cpu_after.txt").split()[1:9]]
    delta = [b - a for a, b in zip(before, after)]
    # Linux guest fields are already included in user/nice: do not count twice.
    total = sum(delta)
    return 100 * (1 - (delta[3] + delta[4]) / total) if total else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root, output = args.raw, args.output
    output.mkdir(parents=True, exist_ok=True)
    design = json.loads(text(root / "design.json"))
    selected_tests = design.get("ab_tests", ["tx", "rx", "udp"])
    expected_trials = design.get("expected_ab_trials", 18)
    rows = []
    trial_temperatures = []
    for trial in sorted(p for p in root.iterdir() if p.is_dir()):
        for filename in ("health_before.txt", "health_during.txt", "health_after.txt"):
            path = trial / filename
            if path.exists():
                trial_temperatures.extend(int(v) / 1000 for v in re.findall(r"max_temp_mc=(\d+)", text(path)))
        match = re.fullmatch(r"P([1-3])_(idle|capture)_(tx|rx|udp)", trial.name)
        if not match:
            continue
        valid, reason, count = verify(trial)
        row = dict(trial=trial.name, rep=int(match[1]), state=match[2], test=match[3],
                   checksum_ok=valid, verified_files=count, valid=False, reason=reason)
        rows.append(row)
        if not valid:
            continue
        if not (trial / "done").exists() or (trial / "guard.txt").exists():
            row["reason"] = "incomplete_or_guarded"
            continue
        data = json.loads(text(trial / "iperf.json"))
        if "error" in data:
            row["reason"] = data["error"]
            continue
        end = data["end"]
        received = end.get("sum_received", end.get("sum", {}))
        row["mbps_received"] = received["bits_per_second"] / 1e6
        row["router_cpu_busy_pct"] = cpu(trial)
        row["iperf_host_cpu_pct"] = end.get("cpu_utilization_percent", {}).get("host_total")
        if match[3] == "udp":
            row["udp_loss_pct"] = received.get("lost_percent")
            row["udp_jitter_ms"] = received.get("jitter_ms")
        else:
            row["tcp_retransmits"] = end.get("sum_sent", {}).get("retransmits")
        if (trial / "hackrf.txt").exists():
            log = text(trial / "hackrf.txt")
            rates = [float(v) for v in re.findall(r"([\d.]+) MiB/second", log)]
            row["hackrf_rate_reports"] = len(rates)
            row["hackrf_mib_s_median"] = stats.median(rates) if rates else None
            row["hackrf_mib_s_min"] = min(rates) if rates else None
            row["hackrf_flagged_lines"] = [line for line in log.splitlines()
                if re.search(r"overflow|underflow|dropped|error|couldn", line, flags=re.I)]
        row["valid"], row["reason"] = True, "completed_and_verified"

    health = text(root / "health.log") if (root / "health.log").exists() else ""
    samples = [tuple(int(v) for v in match) for match in re.findall(
        r"uptime_s=(\d+).*?memavail_kb=(\d+) max_temp_mc=(\d+)", health)]
    reboots = sum(b[0] < a[0] for a, b in zip(samples, samples[1:]))
    all_done = (root / "ALL_DONE").exists()
    temperatures = trial_temperatures + [v[2] / 1000 for v in samples]
    report = {"run": root.name, "design": design, "all_done": all_done,
              "valid_trials": sum(row["valid"] for row in rows), "expected_ab_trials": expected_trials,
              "health_samples": len(samples), "observed_uptime_decreases": reboots,
              "temperature_max_c": max(temperatures, default=None),
              "temperature_min_c": min(temperatures, default=None),
              "memory_min_kib": min((v[1] for v in samples), default=None), "rows": rows}
    metrics = [("TCP 发送吞吐（Mbit/s）", "tx", "mbps_received"),
               ("TCP 接收吞吐（Mbit/s）", "rx", "mbps_received"),
               ("UDP 接收吞吐（Mbit/s）", "udp", "mbps_received"),
               ("UDP 丢包（%）", "udp", "udp_loss_pct"),
               ("UDP 抖动（ms）", "udp", "udp_jitter_ms")]
    summaries = []
    lines = ["# 第 4 轮保守 Wi-Fi 测试结果", "",
             f"数据目录：`{root.name}`。完整结束标记：{all_done}；有效子项：{report['valid_trials']}/{expected_trials}。", "",
             "| 指标 | 空闲逐次值 | 采集逐次值 | 完整配对数 | 配对差中位数（采集−空闲） |",
             "|---|---|---|---|---|"]
    for label, test, metric in metrics:
        if test not in selected_tests:
            continue
        values = {state: {row["rep"]: row.get(metric) for row in rows if row["valid"]
                         and row["state"] == state and row["test"] == test
                         and row.get(metric) is not None} for state in ["idle", "capture"]}
        pairs = sorted(values["idle"].keys() & values["capture"].keys())
        deltas = [values["capture"][rep] - values["idle"][rep] for rep in pairs]
        summary = dict(label=label, test=test, metric=metric, values=values,
                       complete_pairs=pairs, paired_deltas=deltas,
                       paired_delta_median=stats.median(deltas) if deltas else None)
        summaries.append(summary)
        fmt = lambda state: ", ".join(f"{value:.3f}" for _, value in sorted(values[state].items())) or "—"
        difference = f"{stats.median(deltas):+.3f}" if deltas else "—"
        lines.append(f"| {label} | {fmt('idle')} | {fmt('capture')} | {len(pairs)} | {difference} |")
    report["summaries"] = summaries
    lines.extend(["", f"健康监测：{len(samples)} 条；开机时长回退 {reboots} 次。",
                  "", "本组采用主动风扇降温和短时测试，与前两轮独立报告。测试项目以 design.json 为准。",
                  "链路为 MT3000 STA 经上游 AP 到 HUGO；外置 LNA 供电状态按现场确认另记。",
                  "小样本差值仅描述本轮观测，不能据此宣称性能等效或采集提高吞吐。"])
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
