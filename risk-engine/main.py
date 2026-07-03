import os
import ipaddress
from clickhouse_driver import Client
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

# ---------- Hissə 1: ClickHouse ----------
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "admin")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "CHANGE_ME_PASSWORD")

ch = Client(
    host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT,
    user=CLICKHOUSE_USER, password=CLICKHOUSE_PASSWORD,
    database="sentinel"
)

# ---------- Hissə 2: Risk məntiqi ----------
SUSPICIOUS_PORTS = {
    445: 40, 139: 40, 135: 35, 3389: 35, 23: 35,
    1433: 30, 3306: 30, 5432: 30, 22: 20,
}
UNKNOWN_APPS = {"incomplete", "insufficient-data", "unknown-tcp", "unknown-udp"}

# Auto-remediation konfiqurasiyası
BLOCK_THRESHOLD = int(os.getenv("BLOCK_THRESHOLD", "70"))   # bu baldan yuxarı bloklan
EXCLUDE_PRIVATE = os.getenv("EXCLUDE_PRIVATE", "false").lower() == "true"  # daxili IP-ləri çıxar

def is_private(ip):
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False

def calculate_risk_for_ip(src_ip, window_minutes=60):
    rows = ch.execute(f"""
        SELECT
            groupUniqArray(dst_port) AS ports,
            uniq(dst_port) AS unique_ports,
            uniq(dst_ip) AS unique_dsts,
            count() AS total_events,
            countIf(app IN {tuple(UNKNOWN_APPS)}) AS unknown_app_count
        FROM firewall_events
        WHERE src_ip = '{src_ip}'
          AND event_time > now() - INTERVAL {window_minutes} MINUTE
    """)
    if not rows or rows[0][3] == 0:
        return None
    ports, unique_ports, unique_dsts, total_events, unknown_count = rows[0]
    score = 0
    reasons = []
    for p in [p for p in ports if p in SUSPICIOUS_PORTS]:
        score += SUSPICIOUS_PORTS[p]
        reasons.append(f"suspicious_port_{p}")
    if unique_ports >= 20:
        score += 30
        reasons.append(f"port_scan_{unique_ports}_ports")
    if total_events > 0 and (unknown_count / total_events) > 0.3:
        score += 15
        reasons.append("high_unknown_app_ratio")
    score = min(score, 100)
    level = "ALERT" if score >= 70 else "WARNING" if score >= 40 else "OK"
    return {
        "src_ip": src_ip, "risk_score": score, "level": level,
        "reasons": reasons,
        "stats": {
            "unique_ports": unique_ports, "unique_dsts": unique_dsts,
            "total_events": total_events, "unknown_apps": unknown_count,
        }
    }

def get_all_alerts(window_minutes=60, min_score=40):
    ips = ch.execute(f"""
        SELECT DISTINCT src_ip FROM firewall_events
        WHERE event_time > now() - INTERVAL {window_minutes} MINUTE
    """)
    alerts = []
    for (ip,) in ips:
        result = calculate_risk_for_ip(ip, window_minutes)
        if result and result["risk_score"] >= min_score:
            alerts.append(result)
    return sorted(alerts, key=lambda x: -x["risk_score"])

def get_blocklist_ips(window_minutes=60):
    """Bloklanacaq IP-lər: risk >= BLOCK_THRESHOLD, allowlist tətbiq olunur."""
    alerts = get_all_alerts(window_minutes, min_score=BLOCK_THRESHOLD)
    blocked = []
    for a in alerts:
        ip = a["src_ip"]
        # Allowlist: daxili IP-ləri çıxar (konfiqurasiya edilə bilən)
        if EXCLUDE_PRIVATE and is_private(ip):
            continue
        blocked.append(ip)
    return blocked

# ---------- Hissə 3: FastAPI ----------
app = FastAPI(title="Sentinel Risk Engine", version="2.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/risk/{src_ip}")
def risk_for_ip(src_ip: str, window: int = 60):
    result = calculate_risk_for_ip(src_ip, window)
    if result is None:
        return {"error": "no data for this IP", "src_ip": src_ip}
    return result

@app.get("/alerts")
def alerts(window: int = 60, min_score: int = 40):
    return {"alerts": get_all_alerts(window, min_score)}

@app.get("/blocklist", response_class=PlainTextResponse)
def blocklist(window: int = 60):
    """
    Palo Alto External Dynamic List (EDL) formatı:
    Hər sətirdə bir IP, sadə mətn. Palo Alto bu URL-i çəkir.
    """
    ips = get_blocklist_ips(window)
    return "\n".join(ips) + "\n" if ips else "\n"

@app.get("/blocklist/json")
def blocklist_json(window: int = 60):
    """Blocklist + səbəblər (Grafana/audit üçün)."""
    alerts = get_all_alerts(window, min_score=BLOCK_THRESHOLD)
    result = []
    for a in alerts:
        if EXCLUDE_PRIVATE and is_private(a["src_ip"]):
            continue
        result.append({"ip": a["src_ip"], "risk_score": a["risk_score"], "reasons": a["reasons"]})
    return {"blocked": result, "count": len(result)}
