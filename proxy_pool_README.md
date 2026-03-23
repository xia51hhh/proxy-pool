# Proxy Pool

> 自动抓取、并发测试、持久化存储的 HTTP 代理池服务，提供 REST API 与 WebUI 管理界面。

## 特性

- **多源抓取** — 从 6+ 个公开来源获取 HTTP 代理（txt / json 格式）
- **并发测试** — 可配置线程数，实时更新可用代理
- **自动刷新** — 后台定时刷新（默认 10 分钟），可配置
- **磁盘持久化** — 代理池与配置重启不丢失，服务启动立即可用
- **API Key 认证** — 所有 API 接口均需认证
- **WebUI** — 可视化管理：查看、测试、添加、删除代理，修改运行配置

## 项目结构

```
proxy_pool.py          # 主服务（FastAPI + 后台线程）
proxy_pool_ui.html     # WebUI 前端（单文件，内嵌 JS/CSS）
requirements.txt       # Python 依赖
.gitignore
# 运行时自动生成（不提交）
proxy_pool_config.json # 运行配置持久化
proxy_pool_data.json   # 代理池数据持久化
```

## 快速开始

### 本地运行

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PROXY_API_KEY=your-secret-key
python proxy_pool.py
```

服务启动后：
- API: `http://localhost:8318`
- WebUI: `http://localhost:8318/ui`

### systemd 部署（Linux）

```ini
[Unit]
Description=Proxy Pool API Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/root
ExecStart=/root/proxypool-venv/bin/uvicorn proxy_pool:app --host 0.0.0.0 --port 8318
Restart=always
RestartSec=10
Environment=HOME=/root
Environment=PROXY_API_KEY=your-secret-key

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable proxypool && systemctl start proxypool
```

## API 文档

所有接口（除 `/health`、`/ui`）需携带请求头：
```
X-API-Key: your-secret-key
```

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（公开）|
| GET | `/ui` | WebUI 管理界面（公开）|
| GET | `/get` | 随机返回一个可用代理 |
| GET | `/get?country=US` | 按国家筛选代理 |
| GET | `/list?limit=100` | 返回代理列表（按延迟升序）|
| GET | `/stats` | 池状态统计 |
| POST | `/refresh` | 手动触发刷新（非阻塞）|
| GET | `/test-proxy?proxy=host:port` | 测试指定代理连通性 |
| POST | `/add-proxy` | 手动添加代理 |
| POST | `/remove-proxy` | 删除代理 |
| GET | `/config` | 获取运行配置 |
| POST | `/config` | 修改并持久化运行配置 |

### 响应示例

```bash
# 获取一个代理
curl -H "X-API-Key: your-key" http://localhost:8318/get
# {"proxy":"1.2.3.4:8080","ms":312,"country":"US","ok_at":1234567890.0}

# 查看统计
curl -H "X-API-Key: your-key" http://localhost:8318/stats
# {"working":89,"last_refresh":1234567890.0,"refreshing":false,"total_tested":3100,"next_refresh_in":483}
```

### Python 使用示例

```python
import requests

API = "http://localhost:8318"
HEADERS = {"X-API-Key": "your-secret-key"}

def get_proxy():
    info = requests.get(f"{API}/get", headers=HEADERS).json()
    return info["proxy"]  # e.g. "1.2.3.4:8080"

proxy = get_proxy()
resp = requests.get(
    "https://example.com",
    proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"},
    timeout=10
)
```

## 配置项

通过 WebUI、API `/config` 或环境变量均可配置，修改后持久化到 `proxy_pool_config.json`。

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `refresh_interval` | `REFRESH_INTERVAL` | `600` | 自动刷新间隔（秒）|
| `max_workers` | `MAX_WORKERS` | `100` | 并发测试线程数 |
| `timeout` | `PROXY_TIMEOUT` | `8` | 单代理测试超时（秒）|
| `test_url` | `TEST_URL` | `https://api.ipify.org?format=json` | 测试目标 URL |
| API Key | `PROXY_API_KEY` | `proxy-pool-key-change-me` | 认证密钥 |

> 环境变量优先级高于配置文件。

## WebUI 截图功能

- 实时统计面板（可用数、状态、累计测试、下次刷新倒计时）
- 一键触发刷新
- 随机获取代理
- 在线测试任意代理（显示出口 IP）
- 手动添加 / 删除代理
- 代理列表支持搜索、国家筛选、速度筛选、一键导出 txt
- 运行配置修改（持久化）

## License

MIT
