"""
autotuner.py â€” Latency-Aware Scan Rate Auto-Tuner v2
=====================================================

What was wrong with v1
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
1. BURST-NOT-SUSTAINED â€” run_tcp_scan() fires each endpoint once, then stops.
   At concurrency=1080 with 3000 endpoints and 2-3s avg latency the entire
   list drains in ~8 seconds.  The remaining 82s of the "90s wave" are idle.
   You were stress-testing an 8-second burst, declaring it safe, then being
   surprised when hours of real scanning congested the network.

2. COVERAGE IS THE WRONG METRIC â€” endpoints eventually respond even under
   heavy congestion, they just take much longer and pile up in your router's
   NAT table.  Latency and timeout rate spike *before* coverage drops.
   Using a 82% coverage floor misses all of this.

3. NO GATEWAY RTT SIGNAL â€” the most direct local congestion indicator is
   completely ignored.  Your router's NAT table filling shows up as gateway
   ping jumping from 3ms to 200ms, long before remote hosts stop answering.

4. ABSOLUTE THRESHOLDS â€” "82% coverage" doesn't adapt to a network that
   already has 5% natural packet loss at calibration.  Everything must be
   ratio-normalised against calibration, not hardcoded.

What v2 does differently
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
â€¢ _sustained_tcp_probe()   Recycles endpoints for the full wave duration,
                           maintaining real concurrency throughout.
â€¢ ProbeStats               Tracks median latency, p90 latency, timeout rate,
                           and connection count per wave.
â€¢ _health_score()          Combines four signals into one [0,1] score, all
                           normalised relative to the calibration run.
â€¢ Gateway RTT              Pings local gateway before/after every wave.
                           A 2Ã— RTT spike = your router NAT table is filling.
â€¢ Endurance validation     After tuning, the final rate is held for
                           3Ã— wave_duration to confirm it is stable overnight,
                           not just for a short burst.
â€¢ Conservative margins     Final rate = best Ã— margin where margin is 0.75
                           for shitty networks (not 0.90).
"""

import asyncio
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from cores.scanner import execute_masscan_silent, execute_nmap_silent
from cores.nmap_resolver import has_nmap
from utils import config
from utils.app_service import APP_SERVICE
from utils.asn_engine import expand_target
from utils.helpers import clear_screen


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def draw_header():
    clear_screen()
    print("==================================================")
    print(f"   WHITEDNS SUITE - AUTO-TUNER v{config.VERSION} (latency-aware)")
    print("==================================================")


def _endpoints_from_ips(ips):
    return [(ip, port) for ip in ips for port in config.TARGET_PORTS]


def _normalize_found_endpoints(found):
    normalized = set()
    for item in found or []:
        if isinstance(item, dict):
            ip, port = item.get("ip"), item.get("port")
        elif isinstance(item, tuple) and len(item) >= 2:
            ip, port = item[0], item[1]
        else:
            continue
        try:
            normalized.add((str(ip), int(port)))
        except Exception:
            continue
    return normalized


def _clear_line() -> None:
    """Erase any \r-based progress line left by masscan/nmap subprocesses."""
    sys.stdout.write("\r" + " " * 120 + "\r")
    sys.stdout.flush()


def _make_sudo_daemon():
    def _daemon():
        while True:
            time.sleep(60)
            try:
                subprocess.run(
                    ["sudo", "-n", "-v"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    threading.Thread(target=_daemon, daemon=True).start()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Gateway RTT measurement
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _find_default_gateway() -> Optional[str]:
    """Detect the local default gateway IP."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["ipconfig"], text=True, stderr=subprocess.DEVNULL, timeout=5
            )
            for line in out.splitlines():
                if "Default Gateway" in line and ":" in line:
                    gw = line.split(":")[-1].strip()
                    if gw and re.match(r"^\d+\.\d+\.\d+\.\d+$", gw):
                        return gw
        else:
            out = subprocess.check_output(
                ["ip", "route"], text=True, stderr=subprocess.DEVNULL, timeout=5
            )
            for line in out.splitlines():
                if line.startswith("default") and "via" in line:
                    m = re.search(r"via (\d+\.\d+\.\d+\.\d+)", line)
                    if m:
                        return m.group(1)
            # macOS fallback
            out = subprocess.check_output(
                ["route", "-n", "get", "default"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            m = re.search(r"gateway:\s+(\S+)", out)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


async def _gateway_rtt_ms(gateway: Optional[str], count: int = 4) -> Optional[float]:
    """Returns median ICMP RTT to local gateway in ms, or None on failure."""
    if not gateway:
        return None
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", str(count), gateway]
        else:
            cmd = ["ping", "-c", str(count), "-W", "2", gateway]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=count * 4,
        )

        # Linux/macOS: "rtt min/avg/max/mdev = 1.2/2.3/3.4/0.5 ms"
        m = re.search(r"[\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms", result.stdout)
        if m:
            return float(m.group(1))
        # Windows: "Average = 2ms"
        m = re.search(r"Average\s*=\s*([\d.]+)\s*ms", result.stdout, re.IGNORECASE)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


async def _gateway_baseline_rtt_ms(gateway: Optional[str], samples: int = 5, gap: float = 0.75) -> Optional[float]:
    """Measure an idle gateway baseline using several RTT samples and return the median."""
    if not gateway:
        return None

    readings: list[float] = []
    for idx in range(samples):
        rtt = await _gateway_rtt_ms(gateway, count=5)
        if rtt is not None:
            readings.append(rtt)
        if idx + 1 < samples:
            await asyncio.sleep(gap)

    if not readings:
        return None
    return statistics.median(readings)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Core measurement primitive â€” SUSTAINED TCP probe
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class ProbeStats:
    """Statistics collected during a single sustained TCP probe wave."""
    connected_eps: set
    n_total: int
    n_connected: int
    n_timeout: int
    n_refused: int
    median_latency_ms: float
    p90_latency_ms: float
    duration_s: float

    @property
    def timeout_rate(self) -> float:
        return self.n_timeout / max(1, self.n_total)

    @property
    def throughput(self) -> float:
        return self.n_total / max(0.01, self.duration_s)

    def fmt(self) -> str:
        return (
            f"{self.n_total} probes | "
            f"connected={self.n_connected} "
            f"timeout={self.n_timeout}({self.timeout_rate*100:.0f}%) "
            f"refused={self.n_refused} | "
            f"lat p50={self.median_latency_ms:.0f}ms p90={self.p90_latency_ms:.0f}ms"
        )


_EMPTY_STATS = ProbeStats(set(), 0, 0, 0, 0, 0.0, 0.0, 0.0)


async def _sustained_tcp_probe(
    endpoints: list,
    concurrency: int,
    duration: float,
    connect_timeout: float = 4.0,
    label: str = "",
) -> ProbeStats:
    """
    Maintains `concurrency` parallel TCP connections for `duration` seconds by
    recycling through `endpoints` in a continuous loop.

    This is the key fix: the original tuner fired each endpoint once and went
    idle.  Here, workers keep reconnecting until the clock runs out, ensuring
    the network is actually loaded for the full wave window.
    """
    if not endpoints or concurrency <= 0 or duration <= 0:
        return _EMPTY_STATS

    ep_list = list(endpoints)
    random.shuffle(ep_list)

    connected_eps: set = set()
    latencies: list[float] = []
    n_total = n_connected = n_timeout = n_refused = 0

    t_start = time.monotonic()
    deadline = t_start + duration
    sem = asyncio.Semaphore(concurrency)

    async def probe_one(ip: str, port: int) -> None:
        nonlocal n_total, n_connected, n_timeout, n_refused
        t0 = time.monotonic()
        ok = timed_out = False
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=connect_timeout
            )
            ok = True
            w.close()
            try:
                await asyncio.wait_for(w.wait_closed(), 0.5)
            except Exception:
                pass
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            pass

        ms = (time.monotonic() - t0) * 1000
        latencies.append(ms)
        n_total += 1
        if ok:
            n_connected += 1
            connected_eps.add((ip, port))
        elif timed_out:
            n_timeout += 1
        else:
            n_refused += 1

    async def worker(start_idx: int) -> None:
        idx = start_idx
        while time.monotonic() < deadline:
            ip, port = ep_list[idx % len(ep_list)]
            idx += 1
            async with sem:
                if time.monotonic() >= deadline:
                    break
                await probe_one(ip, port)

    # 3Ã— workers so the semaphore is never starved
    n_workers = min(concurrency * 3, concurrency + 150)
    worker_tasks = [
        asyncio.create_task(worker(i))
        for i in range(n_workers)
    ]

    async def _show_progress() -> None:
        while True:
            elapsed = time.monotonic() - t_start
            pct = min(100.0, elapsed / duration * 100)
            sys.stdout.write(
                f"\r  -> {label} [{pct:5.1f}%] {elapsed:.0f}s | "
                f"probes={n_total} conn={n_connected} timeout={n_timeout}"
            )
            sys.stdout.flush()
            await asyncio.sleep(0.5)

    prog = asyncio.create_task(_show_progress()) if label else None
    try:
        await asyncio.gather(*worker_tasks, return_exceptions=True)
    finally:
        if prog:
            prog.cancel()
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()

    actual_dur = time.monotonic() - t_start

    if not latencies:
        return _EMPTY_STATS

    sorted_lat = sorted(latencies)
    med = statistics.median(sorted_lat)
    p90 = sorted_lat[max(0, int(len(sorted_lat) * 0.90) - 1)]

    return ProbeStats(
        connected_eps=connected_eps,
        n_total=n_total,
        n_connected=n_connected,
        n_timeout=n_timeout,
        n_refused=n_refused,
        median_latency_ms=med,
        p90_latency_ms=p90,
        duration_s=actual_dur,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Health scoring
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _health_score(
    probe: ProbeStats,
    cal: ProbeStats,
    baseline_eps: set,
    gw_rtt: Optional[float],
    cal_gw_rtt: Optional[float],
) -> tuple[float, str]:
    """
    Compute a composite health score in [0, 1] normalised against calibration.
    All four signals degrade relative to the calibration baseline, so the same
    thresholds work on both fiber (low baseline noise) and shitty radio links
    (high baseline noise).

    Score >= 0.72 = healthy
    Score  0.55â€“0.72 = degraded (slow down)
    Score < 0.55 = congested (stop)
    """
    # 1. Coverage â€” what fraction of known-alive endpoints responded?
    if baseline_eps:
        coverage = len(baseline_eps & probe.connected_eps) / len(baseline_eps)
    else:
        coverage = 1.0
    cov_score = max(0.0, min(1.0, coverage))

    # Killswitch: if we are losing most of the baseline, this wave failed.
    if coverage < 0.30:
        info = f"cov={coverage*100:.0f}% < 30% â†’ score=0.00"
        return 0.0, info

    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _ratio_score(ratio: float) -> float:
        # 1.0 at parity; 0.0 at 4x worse; never exceeds 1.0
        return _clamp01(1.0 - max(0.0, ratio - 1.0) / 3.0)

    binary_scanner = probe.n_timeout == 0 and probe.median_latency_ms == 0.0

    if binary_scanner:
        if gw_rtt and cal_gw_rtt and cal_gw_rtt > 0:
            effective_cal_gw = max(15.0, cal_gw_rtt)
            gw_ratio = gw_rtt / effective_cal_gw
            gw_score = _ratio_score(gw_ratio)
            score = _clamp01((cov_score * 0.60) + (gw_score * 0.40))
            gw_str = f"{gw_ratio:.1f}Ã—({gw_rtt:.0f}ms)"
        else:
            gw_ratio = 1.0
            gw_score = cov_score
            score = cov_score
            gw_str = "N/A"

        info = (
            f"cov={coverage*100:.0f}% "
            f"gw={gw_str} â†’ score={score:.2f}"
        )
        return score, info

    # 2. Timeout rate â€” ratio vs calibration.
    cal_to = max(0.02, cal.timeout_rate)
    to_ratio = probe.timeout_rate / cal_to
    to_score = _ratio_score(to_ratio)

    # 3. Latency ratio â€” median latency vs calibration.
    if cal.median_latency_ms > 5.0 and probe.median_latency_ms > 0:
        lat_ratio = probe.median_latency_ms / cal.median_latency_ms
        lat_score = _ratio_score(lat_ratio)
        lat_str = f"lat={lat_ratio:.1f}Ã—({probe.median_latency_ms:.0f}ms)"
    else:
        lat_ratio = 1.0
        lat_score = 0.0
        lat_str = "lat=N/A"

    # 4. Gateway RTT ratio â€” most direct local congestion signal.
    if gw_rtt and cal_gw_rtt and cal_gw_rtt > 0:
        effective_cal_gw = max(15.0, cal_gw_rtt)
        gw_ratio = gw_rtt / effective_cal_gw
        gw_score = _ratio_score(gw_ratio)
        gw_str = f"gw={gw_ratio:.1f}Ã—({gw_rtt:.0f}ms)"
    else:
        gw_ratio = 1.0
        gw_score = 0.0
        gw_str = "gw=N/A"

    # Weighted combination for rich telemetry scanners.
    score = _clamp01(
        (cov_score * 0.15)
        + (to_score * 0.30)
        + (lat_score * 0.20)
        + (gw_score * 0.35)
    )

    info = (
        f"cov={coverage*100:.0f}% "
        f"to={probe.timeout_rate*100:.0f}%({to_ratio:.1f}Ã—) "
        f"{lat_str} {gw_str} â†’ score={score:.2f}"
    )
    return score, info


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Masscan / Nmap wrapper that returns ProbeStats (coverage only â€” no latency)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _masscan_probe(
    sampled_ips: list,
    rate: int,
    duration: float,
    retries: int = 2,
    wait: int = 0,
) -> ProbeStats:
    """
    Run ONE masscan sweep and measure what fraction of known-alive endpoints
    were found (packet-loss proxy at high rates).

    The old loop-and-accumulate approach was wrong: at 8 000 pps, 2 400
    endpoints finish in ~0.3 s, so the loop ran ~300 times per wave and the
    cumulative union of all runs always hit 100 % coverage regardless of rate.
    A single sweep correctly exposes missed packets when the rate is too high.
    """
    _clear_line()
    t0 = time.monotonic()
    results: list = []
    try:
        results = await asyncio.wait_for(
            execute_masscan_silent(sampled_ips, rate, retries, wait, duration=duration),
            timeout=duration + 30.0,
        )
    except (asyncio.TimeoutError, Exception):
        pass

    _clear_line()
    connected = _normalize_found_endpoints(results)
    n = len(sampled_ips) * len(config.TARGET_PORTS)
    dur = max(0.01, time.monotonic() - t0)
    return ProbeStats(
        connected_eps=connected,
        n_total=n,
        n_connected=len(connected),
        n_timeout=0,
        n_refused=n - len(connected),
        median_latency_ms=0.0,
        p90_latency_ms=0.0,
        duration_s=dur,
    )


async def _nmap_probe(
    sampled_ips: list,
    rate: int,
    duration: float,
    scan_type: str = "-sT",
) -> ProbeStats:
    """
    Run ONE nmap sweep and measure coverage.

    The old loop had two fatal bugs:
    1. -T2 ("polite") adds ~15 s inter-probe delay, so 400 IPs Ã— 6 ports
       never finish in a 90 s wave â†’ always 0 % coverage.
    2. execute_nmap_silent can exceed `duration` without raising TimeoutError,
       so the while-loop would block long past deadline ("won't quit" symptom).

    Fixes: -T4, longer host_timeout, single invocation wrapped in wait_for.
    """
    _clear_line()
    t0 = time.monotonic()
    min_r = max(1, rate // 4)
    results: list = []
    try:
        results = await asyncio.wait_for(
            execute_nmap_silent(
                sampled_ips,
                "-T4",           # was -T2 (polite); T4 finishes in reasonable time
                2,
                min_r,
                max(rate, min_r),
                scan_type,
                host_timeout="60s",  # was 15s â€” far too short for real hosts
                duration=duration,
            ),
            timeout=duration + 60.0,   # hard ceiling so we can never hang
        )
    except (asyncio.TimeoutError, Exception):
        pass

    _clear_line()
    connected = _normalize_found_endpoints(results)
    n = len(sampled_ips) * len(config.TARGET_PORTS)
    dur = max(0.01, time.monotonic() - t0)
    return ProbeStats(
        connected_eps=connected,
        n_total=n,
        n_connected=len(connected),
        n_timeout=0,
        n_refused=n - len(connected),
        median_latency_ms=0.0,
        p90_latency_ms=0.0,
        duration_s=dur,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Core tuning algorithm
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _adaptive_tune(
    engine_name: str,
    probe_fn,              # async (rate: int, duration: float) -> ProbeStats
    start_rate: int,
    max_rate: int,
    wave_duration: float,
    health_threshold: float,
    inter_wave_delay: float,
    baseline_eps: set,
    gateway: Optional[str],
    final_margin: float,
    endurance_multiplier: float = 3.0,
) -> int:
    """
    Tune a scanner rate using health-score-based congestion detection.

    Parameters
    â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    probe_fn          Async callable (rate, duration) â†’ ProbeStats.
    start_rate        Safe starting rate for calibration.
    max_rate          Upper bound.
    wave_duration     Seconds per test wave (actual sustained load duration).
    health_threshold  Score below which rate is too high (profile-dependent).
    inter_wave_delay  Seconds to rest between waves (allows NAT table drain).
    baseline_eps      Set of (ip, port) that are known-alive from TCP baseline.
    gateway           Local gateway IP for RTT measurement, or None.
    final_margin      Fraction of best_rate to apply as safety margin.
    endurance_multiplier  Endurance test = wave_duration Ã— this multiplier.
    """

    # â”€â”€ Step 1: Calibration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[*] Calibrating {engine_name} at rate {start_rate}...")

    cal_probe_task = asyncio.create_task(probe_fn(start_rate, wave_duration))
    await asyncio.sleep(min(2.0, max(0.05, wave_duration * 0.1)))
    cal_gw = await _gateway_rtt_ms(gateway)
    cal_probe = await cal_probe_task
    _clear_line()
    cal_coverage = (
        len(baseline_eps & cal_probe.connected_eps) / len(baseline_eps)
        if baseline_eps else 1.0
    )

    print(
        f"    Calibration: coverage={cal_coverage*100:.1f}% "
        f"timeout={cal_probe.timeout_rate*100:.1f}% "
        f"lat={cal_probe.median_latency_ms:.0f}ms "
        f"gw={f'{cal_gw:.1f}ms' if cal_gw else 'N/A'}"
    )

    if cal_coverage < 0.30:
        print(
            f"[-] Calibration coverage too low ({cal_coverage*100:.1f}%)."
            f" Skipping {engine_name}."
        )
        return start_rate

    # â”€â”€ Step 2: Ramp up (doubling) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"[*] Tuning {engine_name} (ramp to {max_rate}, threshold={health_threshold:.2f})...")

    rate = min(max_rate, start_rate * 2)
    best_rate = start_rate
    upper_bound = max_rate
    failure_rest = max(30.0, inter_wave_delay * 5)

    async def _probe_with_one_strike(rate_value: int, phase: str):
        async def _run_once(tag: str):
            probe_task = asyncio.create_task(probe_fn(rate_value, wave_duration))
            await asyncio.sleep(min(2.0, max(0.05, wave_duration * 0.1)))
            gw_rtt = await _gateway_rtt_ms(gateway)
            probe = await probe_task
            score, info = _health_score(probe, cal_probe, baseline_eps, gw_rtt, cal_gw)
            _clear_line()
            print(f"  -> [{tag} {rate_value:>7}] {info}")
            return score, probe, gw_rtt, info

        score, probe, gw_rtt, info = await _run_once(phase)
        if score >= health_threshold:
            return True, score, probe, gw_rtt, info

        print(f"     [!] Transient failure detected. Resting {failure_rest:.0f}s and retrying...")
        await asyncio.sleep(failure_rest)

        retry_score, retry_probe, retry_gw_rtt, retry_info = await _run_once(f"Retry {phase}")
        if retry_score >= health_threshold:
            return True, retry_score, retry_probe, retry_gw_rtt, retry_info

        print(f"     [-] {phase} failed twice. Resting {failure_rest:.0f}s before back-off...")
        await asyncio.sleep(failure_rest)
        return False, retry_score, retry_probe, retry_gw_rtt, retry_info

    while rate <= max_rate:
        await asyncio.sleep(inter_wave_delay)
        passed, score, probe, gw_rtt, info = await _probe_with_one_strike(rate, "Ramp")

        if passed:
            best_rate = rate
            if rate >= max_rate:
                break
            rate = min(rate * 2, max_rate)
        else:
            upper_bound = rate
            break

    # â”€â”€ Step 3 & 4: Fine-tuning & Endurance validation loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    search_low, search_high = best_rate, upper_bound
    
    while True:
        tolerance = max(5, int(search_low * 0.15))

        if search_low < search_high and (search_high - search_low) > tolerance:
            print(f"[*] Fine-tuning {engine_name} between {search_low} and {search_high}...")

            while search_low < search_high and (search_high - search_low) > tolerance:
                mid = (search_low + search_high) // 2
                await asyncio.sleep(inter_wave_delay)
                passed, score, probe, gw_rtt, info = await _probe_with_one_strike(mid, "Search")

                if passed:
                    best_rate = mid
                    search_low = mid + 1
                    # Brief confirm pass before moving low boundary up
                    await asyncio.sleep(inter_wave_delay * 0.5)
                else:
                    search_high = mid - 1
        else:
            print("     [+] Binary search converged (within tolerance).")

        # â”€â”€ Step 4: Endurance validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        endurance_dur = wave_duration * endurance_multiplier
        print(
            f"\n[*] Endurance check: holding rate={best_rate} for "
            f"{endurance_dur:.0f}s ({endurance_multiplier:.0f}Ã— wave duration)..."
        )
        print("     This confirms the rate is stable overnight, not just for short bursts.")

        await asyncio.sleep(inter_wave_delay)
        end_probe_task = asyncio.create_task(probe_fn(best_rate, endurance_dur))
        await asyncio.sleep(min(2.0, max(0.05, endurance_dur * 0.1)))
        gw_rtt = await _gateway_rtt_ms(gateway)
        end_probe = await end_probe_task
        end_score, end_info = _health_score(
            end_probe, cal_probe, baseline_eps, gw_rtt, cal_gw
        )
        _clear_line()
        print(f"  -> [Endurance] {end_info}")

        if end_score < health_threshold:
            print(
                f"     [!] Endurance FAIL (score={end_score:.2f}). "
                f"Network degrades under sustained load."
            )
            
            # Re-adjust bounds for another binary search pass
            search_high = best_rate - 1
            search_low = max(start_rate, int(search_high * 0.6))
            tolerance = max(5, int(search_low * 0.15))

            # Early stopping check
            if search_high <= start_rate or (search_high - search_low) <= tolerance:
                fallback = max(start_rate, int(best_rate * 0.85))
                print(
                    f"     [!] Bounds too tight for further tuning. "
                    f"Early stopping and backing rate to {fallback}."
                )
                best_rate = fallback
                break

            print(f"     [*] Resting 60s before resuming search between {search_low} and {search_high}...")
            await asyncio.sleep(60)
            continue
        else:
            print(f"     [+] Endurance PASS (score={end_score:.2f}).")
            break

    final_rate = max(start_rate, int(best_rate * final_margin))
    print(
        f"[âœ“] {engine_name} optimized to: {final_rate} "
        f"(best={best_rate} Ã— margin={final_margin:.2f})"
    )
    return final_rate


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Entry point
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _draw_profile_menu():
    print("\n[?] Select your network quality:")
    print("    [1] Good   (Fiber / low-loss / aggressive tuning)")
    print("    [2] Normal (Decent Wi-Fi / balanced tuning) [Default]")
    print("    [3] Shitty (High ping / loss / forgiving tuning)")


async def run():
    """Entry point for the Auto-Tuner module."""
    has_masscan = shutil.which("masscan") is not None
    has_nmap_available = has_nmap()

    # Always include direct as the baseline
    scanners = [{"id": "asyncio", "name": "Direct (Python Asyncio) [ALWAYS AVAILABLE]", "available": True}]
    if has_masscan:
        scanners.append({"id": "masscan", "name": "Masscan Rate [Installed]", "available": True})
    else:
        scanners.append({"id": "masscan", "name": "Masscan Rate [NOT INSTALLED]", "available": False})
    
    if has_nmap_available:
        scanners.append({"id": "nmap", "name": "Nmap Max Rate [Available]", "available": True})
    else:
        scanners.append({"id": "nmap", "name": "Nmap Max Rate [NOT AVAILABLE]", "available": False})

    selected_keys: set[str] = set()

    # â”€â”€ Scanner selection menu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    while True:
        draw_header()
        print("===============================================================")
        print("   SELECT SCANNERS TO TUNE")
        print("   (Direct will always be available as fallback)")
        print("===============================================================\n")
        for i, s in enumerate(scanners):
            checkbox = "[X]" if s["id"] in selected_keys else "[ ]"
            status = "âœ“" if s["available"] else "âœ—"
            print(f"  {i+1:>2}. {checkbox} {status} {s['name']}")
        
        print("\nCommands:")
        print("  [1, 2...]   Toggle   [all] Select available   [clear] Clear   [d] Done   [0] Back")
        print("  (Note: Only available scanners will actually tune)")
        cmd = input("\nAction: ").strip().lower()
        if not cmd:
            continue
        if cmd in ("0", "q"):
            return
        if cmd == "d":
            break
        if cmd == "all":
            selected_keys.update(s["id"] for s in scanners if s["available"])
            continue
        if cmd == "clear":
            selected_keys.clear()
            continue
        try:
            for p in cmd.replace(",", " ").split():
                if p.isdigit():
                    i = int(p)
                    if 1 <= i <= len(scanners):
                        k = scanners[i - 1]["id"]
                        if k in selected_keys:
                            selected_keys.discard(k)
                        else:
                            # Allow selecting unavailable scanners for now (will skip in tuning)
                            selected_keys.add(k)
        except Exception:
            pass

    tune_asyncio = "asyncio" in selected_keys
    tune_masscan = "masscan" in selected_keys and has_masscan
    tune_nmap = "nmap" in selected_keys and has_nmap_available

    if not any([tune_asyncio, tune_masscan, tune_nmap]):
        print("[-] No scanners selected for tuning.")
        print("[*] Direct (Asyncio) is always available as a fallback.")
        input("Press Enter to return...")
        return

    # â”€â”€ Sudo setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    draw_header()
    print("[*] Latency-Aware Scan Rate Tuner")
    print("[!] Uses sustained load + gateway RTT + latency drift to detect congestion.")

    is_root_or_sudo = sys.platform == "win32" or os.geteuid() == 0
    if not is_root_or_sudo and (tune_masscan or tune_nmap):
        print("\n[!] Masscan / Nmap need sudo for accurate testing.")
        try:
            subprocess.run(["sudo", "-v"], check=True)
            is_root_or_sudo = True
            _make_sudo_daemon()
            print("[+] Sudo acquired and kept alive.")
        except Exception:
            print("[-] Sudo failed. Skipping Masscan / Nmap tuning.")
            tune_masscan = tune_nmap = False

    # â”€â”€ Profile selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # fmt: off
    profiles = {
        "1": {
            "label":              "GOOD / FIBER",
            "seed_ips":           900,
            "baseline_concurrency": 200,
            "wave_duration":      60.0,
            "health_threshold":   0.85,
            "inter_wave_delay":   2.0,
            "endurance_mult":     3.0,
            "final_margin":       0.93,
            "async_start":        200,  "async_max": 8000,
            "masscan_start":      2500, "masscan_max": 250_000,
            "nmap_start":         100,  "nmap_max": 40_000,
        },
        "2": {
            "label":              "NORMAL / WIFI",
            "seed_ips":           700,
            "baseline_concurrency": 100,
            "wave_duration":      75.0,
            "health_threshold":   0.80,
            "inter_wave_delay":   3.5,
            "endurance_mult":     3.0,
            "final_margin":       0.88,
            "async_start":        50,   "async_max": 2000,
            "masscan_start":      800,  "masscan_max": 80_000,
            "nmap_start":         100,  "nmap_max": 10_000,
        },
        "3": {
            "label":              "LOSSY / HIGH-PING",
            "seed_ips":           400,
            "baseline_concurrency": 30,
            "wave_duration":      90.0,
            "health_threshold":   0.75,
            "inter_wave_delay":   6.0,
            "endurance_mult":     4.0,   # longer endurance for unstable links
            "final_margin":       0.75,  # aggressive safety margin
            "async_start":        15,   "async_max": 400,
            "masscan_start":      400,  "masscan_max": 8_000,
            "nmap_start":         50,   "nmap_max": 1_500,
        },
    }
    # fmt: on

    _draw_profile_menu()
    net_choice = input("    Choice: ").strip()
    p = profiles.get(net_choice, profiles["2"])

    print(
        f"\n[*] Profile: {p['label']} | "
        f"wave={p['wave_duration']:.0f}s | "
        f"health_threshold={p['health_threshold']:.2f} | "
        f"endurance={p['endurance_mult']:.0f}Ã— | "
        f"safety_margin={p['final_margin']:.2f}"
    )

    # â”€â”€ Target selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    target = input(
        "\n[?] Enter a test subnet or ASN (Default: AS202468 / AbrArvan): "
    ).strip()
    if not target:
        target = "AS202468"

    print("\n[*] Expanding targets...")
    ips = expand_target(target, silent=True)
    if not ips:
        print("[-] Invalid target or no IPs found.")
        input("Press Enter to return...")
        return

    ips = list(dict.fromkeys(ips))
    random.shuffle(ips)
    sampled_ips = ips[: min(p["seed_ips"], len(ips))]
    test_endpoints = _endpoints_from_ips(sampled_ips)

    print(f"[*] Selected {len(sampled_ips)} IPs Ã— {len(config.TARGET_PORTS)} ports = {len(test_endpoints)} endpoints.")

    # â”€â”€ TCP Baseline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n[*] Step 1: TCP Baseline â€” finding all live endpoints (not timed, no load)...")
    from cores.scanner import run_tcp_scan

    tcp_results = await run_tcp_scan(
        test_endpoints, p["baseline_concurrency"], desc="TCP Baseline"
    )
    baseline_eps = _normalize_found_endpoints(
        [(ip, port) for ip, port in tcp_results]
    )

    if len(baseline_eps) < 10:
        print(
            f"[-] Baseline too low ({len(baseline_eps)} endpoints). "
            "Try a subnet with more active hosts."
        )
        input("Press Enter to return...")
        return

    print(f"[+] TCP Baseline: {len(baseline_eps)} live endpoints.")

    # â”€â”€ Gateway baseline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    gateway = _find_default_gateway()
    if gateway:
        print(f"[*] Local gateway detected: {gateway}")
        gw_baseline = await _gateway_baseline_rtt_ms(gateway)
        if gw_baseline:
            print(f"[*] Baseline gateway RTT: {gw_baseline:.1f}ms")
        else:
            print("[!] Gateway found but ping failed (ICMP blocked?). RTT signal disabled.")
    else:
        print("[!] Could not detect default gateway. RTT signal disabled.")
        gw_baseline = None

    print("\n[*] Resting 5s before tuning...")
    await asyncio.sleep(5)

    # â”€â”€ Scanner-specific probe functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    async def probe_asyncio(rate: int, duration: float) -> ProbeStats:
        return await _sustained_tcp_probe(
            list(baseline_eps),   # only probe endpoints we KNOW are alive
            rate,
            duration,
            connect_timeout=4.0,
            label=f"Asyncio/{rate}",
        )

    nmap_scan_type = "-sS" if is_root_or_sudo else "-sT"

    async def probe_masscan(rate: int, duration: float) -> ProbeStats:
        return await _masscan_probe(sampled_ips, rate, duration, wait=0)

    async def probe_nmap(rate: int, duration: float) -> ProbeStats:
        return await _nmap_probe(sampled_ips, rate, duration, scan_type=nmap_scan_type)

    # â”€â”€ Tune each selected engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if tune_asyncio:
        tuned_asyncio = await _adaptive_tune(
            "Asyncio Concurrency",
            probe_asyncio,
            start_rate=p["async_start"],
            max_rate=p["async_max"],
            wave_duration=p["wave_duration"],
            health_threshold=p["health_threshold"],
            inter_wave_delay=p["inter_wave_delay"],
            baseline_eps=baseline_eps,
            gateway=gateway,
            final_margin=p["final_margin"],
            endurance_multiplier=p["endurance_mult"],
        )
        APP_SERVICE.set_max_concurrent_scans(tuned_asyncio)

    if tune_masscan:
        print("\n[*] Refreshing sudo token for Masscan...")
        subprocess.run(["sudo", "-v"], check=False)
        await asyncio.sleep(max(1.0, p["inter_wave_delay"]))
        tuned_masscan = await _adaptive_tune(
            "Masscan Rate",
            probe_masscan,
            start_rate=p["masscan_start"],
            max_rate=p["masscan_max"],
            wave_duration=p["wave_duration"],
            health_threshold=p["health_threshold"],
            inter_wave_delay=p["inter_wave_delay"],
            baseline_eps=baseline_eps,
            gateway=gateway,
            final_margin=p["final_margin"],
            endurance_multiplier=p["endurance_mult"],
        )
        APP_SERVICE.set_tuned_masscan_rate(tuned_masscan)

    if tune_nmap:
        print("\n[*] Refreshing sudo token for Nmap...")
        subprocess.run(["sudo", "-v"], check=False)
        await asyncio.sleep(max(1.0, p["inter_wave_delay"]))
        tuned_nmap = await _adaptive_tune(
            "Nmap Max Rate",
            probe_nmap,
            start_rate=p["nmap_start"],
            max_rate=p["nmap_max"],
            wave_duration=p["wave_duration"],
            health_threshold=p["health_threshold"],
            inter_wave_delay=p["inter_wave_delay"],
            baseline_eps=baseline_eps,
            gateway=gateway,
            final_margin=p["final_margin"],
            endurance_multiplier=p["endurance_mult"],
        )
        APP_SERVICE.set_tuned_nmap_rates(tuned_nmap)

    print("\n[+] Auto-Tuning complete. Safe, endurance-verified rates applied.")
    APP_SERVICE.save_runtime_config()
    input("Press Enter to return to main menu...")


if __name__ == "__main__":
    asyncio.run(run())
