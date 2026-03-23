#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, json, os, random, subprocess, threading, time
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException, Query, Security, Request
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_pool_config.json")
POOL_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_pool_data.json")

CONFIG_DEFAULTS = {
    "refresh_interval": 600,
    "max_workers": 100,
    "timeout": 8,
    "test_url": "https://api.ipify.org?format=json",
}

def _load_config() -> dict:
    cfg = dict(CONFIG_DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            for k in CONFIG_DEFAULTS:
                if k in saved:
                    cfg[k] = saved[k]
        except Exception:
            pass
    # env overrides file
    if os.environ.get("REFRESH_INTERVAL"): cfg["refresh_interval"] = int(os.environ["REFRESH_INTERVAL"])
    if os.environ.get("MAX_WORKERS"): cfg["max_workers"] = int(os.environ["MAX_WORKERS"])
    if os.environ.get("PROXY_TIMEOUT"): cfg["timeout"] = int(os.environ["PROXY_TIMEOUT"])
    if os.environ.get("TEST_URL"): cfg["test_url"] = os.environ["TEST_URL"]
    return cfg

def _save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, indent=2)
    except Exception as e:
        print(f"[config] save failed: {e}")

CONFIG = _load_config()

SOURCES_TXT = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/http.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http",
]
SOURCES_JSON = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/http.json",
    "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=100&page=1&sort_by=lastChecked&sort_type=desc",
]

class ProxyPool:
    def __init__(self):
        self._lock = threading.Lock()
        self._pool: dict[str, dict] = {}
        self._last_refresh: float = 0
        self._refreshing: bool = False
        self._total_tested: int = 0

    def _fetch(self):
        c: dict[str, dict] = {}
        for url in SOURCES_TXT:
            try:
                r = requests.get(url, timeout=12)
                if r.status_code == 200:
                    for line in r.text.splitlines():
                        line = line.strip()
                        if line and ":" in line and not line.startswith("#"):
                            c.setdefault(line, {})
            except Exception: pass
        for url in SOURCES_JSON:
            try:
                r = requests.get(url, timeout=12)
                if r.status_code != 200: continue
                j = r.json()
                if isinstance(j, list):
                    for it in j:
                        if isinstance(it, dict):
                            p = it.get("proxy") or (f"{it['ip']}:{it['port']}" if it.get("ip") else None)
                            if p: c.setdefault(p, {})["country"] = it.get("country") or it.get("country_code", "")
                elif isinstance(j, dict) and isinstance(j.get("data"), list):
                    for it in j["data"]:
                        ip, port = it.get("ip"), it.get("port")
                        if ip and port: c.setdefault(f"{ip}:{port}", {})["country"] = it.get("country") or it.get("country_code", "")
            except Exception: pass
        return c

    def _test(self, proxy: str):
        try:
            t0 = time.time()
            cp = subprocess.run(["curl", "-sS", "--max-time", str(CONFIG["timeout"]), "-x", proxy, CONFIG["test_url"]], capture_output=True, text=True)
            if cp.returncode == 0 and cp.stdout.strip():
                return proxy, int((time.time()-t0)*1000), cp.stdout.strip()
        except Exception: pass
        return None

    def refresh(self):
        with self._lock:
            if self._refreshing: return
            self._refreshing = True
        try:
            candidates = self._fetch()
            fresh: dict[str, dict] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as ex:
                futures = {ex.submit(self._test, p): p for p in candidates}
                for f in concurrent.futures.as_completed(futures):
                    res = f.result()
                    if res:
                        p, ms, _ = res
                        cc = candidates.get(p, {}).get("country", "")
                        fresh[p] = {"ms": ms, "country": cc, "ok_at": time.time()}
                        with self._lock:
                            self._pool[p] = fresh[p]
                            self._total_tested += 1
            with self._lock:
                self._pool = fresh
                self._last_refresh = time.time()
        finally:
            with self._lock:
                self._refreshing = False

    def start_background(self):
        self._load_pool()
        def _loop():
            while True:
                self.refresh()
                self._save_pool()
                time.sleep(CONFIG["refresh_interval"])
        threading.Thread(target=_loop, daemon=True).start()

    def get_one(self, country=""):
        with self._lock: pool = dict(self._pool)
        if not pool: return None
        if country:
            f = {p:v for p,v in pool.items() if (v.get("country") or "").upper()==country.upper()}
            pool = f or pool
        p, meta = random.choice(list(pool.items()))
        return {"proxy": p, **meta}

    def get_all(self):
        with self._lock:
            return sorted([{"proxy":p,**v} for p,v in self._pool.items()], key=lambda x:x["ms"])

    def stats(self):
        with self._lock:
            return {"working":len(self._pool),"last_refresh":self._last_refresh,"refreshing":self._refreshing,"total_tested":self._total_tested,"next_refresh_in":max(0,int(CONFIG["refresh_interval"]-(time.time()-self._last_refresh)))}

    def _load_pool(self):
        if not os.path.exists(POOL_FILE):
            return
        try:
            with open(POOL_FILE, encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._pool = {p: v for p, v in data.items()}
            print(f"[pool] loaded {len(self._pool)} proxies from disk")
        except Exception as e:
            print(f"[pool] load from disk failed: {e}")

    def _save_pool(self):
        try:
            with self._lock:
                data = dict(self._pool)
            with open(POOL_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[pool] save to disk failed: {e}")

    def add(self, proxy, country="", ms=0):
        with self._lock: self._pool[proxy] = {"ms":ms,"country":country,"ok_at":time.time()}

    def remove(self, proxy):
        with self._lock: self._pool.pop(proxy, None)

    def test_one(self, proxy):
        res = self._test(proxy)
        if res:
            p, ms, out = res
            try: ip = json.loads(out).get("ip","")
            except: ip = out
            return {"ok":True,"proxy":p,"ms":ms,"ip":ip}
        return {"ok":False,"proxy":proxy,"error":"连接失败或超时"}


API_KEY = os.environ.get("PROXY_API_KEY", "proxy-pool-key-change-me")
_hdr = APIKeyHeader(name="X-API-Key", auto_error=False)
def verify_key(key: str = Security(_hdr)):
    if key != API_KEY: raise HTTPException(401, detail="Invalid or missing API key.")

pool = ProxyPool()
app = FastAPI(title="Proxy Pool")

@app.on_event("startup")
async def startup(): pool.start_background()

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/ui", response_class=HTMLResponse)
def webui():
    with open(os.path.join(os.path.dirname(__file__), "proxy_pool_ui.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/get", dependencies=[Security(verify_key)])
def get_proxy(country: str = Query("")):
    item = pool.get_one(country=country)
    if not item: raise HTTPException(503, detail="No working proxies available yet.")
    return item

@app.get("/list", dependencies=[Security(verify_key)])
def list_proxies(limit: int = Query(500, ge=1, le=2000)):
    items = pool.get_all()[:limit]
    return {"count": len(items), "proxies": items}

@app.get("/stats", dependencies=[Security(verify_key)])
def get_stats(): return pool.stats()

@app.post("/refresh", dependencies=[Security(verify_key)])
def trigger_refresh():
    threading.Thread(target=pool.refresh, daemon=True).start()
    return {"message":"refresh started"}

@app.get("/test-proxy", dependencies=[Security(verify_key)])
def test_proxy_api(proxy: str = Query(...)): return pool.test_one(proxy)

@app.post("/add-proxy", dependencies=[Security(verify_key)])
async def add_proxy(request: Request):
    body = await request.json()
    proxy = body.get("proxy","").strip()
    if not proxy: raise HTTPException(400, detail="proxy required")
    pool.add(proxy, country=body.get("country",""))
    return {"message":f"added {proxy}"}

@app.post("/remove-proxy", dependencies=[Security(verify_key)])
async def remove_proxy(request: Request):
    body = await request.json()
    pool.remove(body.get("proxy","").strip())
    return {"message":"removed"}

@app.get("/config", dependencies=[Security(verify_key)])
def get_config(): return CONFIG

@app.post("/config", dependencies=[Security(verify_key)])
async def set_config(request: Request):
    body = await request.json()
    for k in ("refresh_interval","max_workers","timeout"):
        if k in body and isinstance(body[k],int) and body[k]>0: CONFIG[k]=body[k]
    if body.get("test_url"): CONFIG["test_url"]=body["test_url"]
    _save_config()
    return CONFIG

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("proxy_pool:app", host="0.0.0.0", port=8318, reload=False)
