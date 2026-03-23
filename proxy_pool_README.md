# Proxy Pool

自动抓取、测试并提供可用 HTTP 代理的服务，带 REST API 和 WebUI。

## 功能

- 多源抓取公开 HTTP 代理（TXT + JSON 格式）
- 并发测试存活，实时更新池
- 每 N 分钟自动刷新（可配置）
- 磁盘持久化：配置与代理池重启不丢失
- REST API（需 API Key 认证）
- WebUI 管理界面：查看、测试、添加、删除代理，修改运行配置

## 文件说明

| 文件 | 说明 |
|------|------|
| `proxy_pool.py` | 主服务（FastAPI）|
| `proxy_pool_ui.html` | WebUI 前端 |
| `proxy_pool_config.json` | 运行配置（自动生成，勿提交）|
| `proxy_pool_data.json` | 代理池数据（自动生成，勿提交）|

## 快速部署

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PROXY_API_KEY=your-secret-key
uvicorn proxy_pool:app --host 0.0.0.0 --port 8318
```

### systemd 服务示例

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

## API

所有接口（除 `/health` `/ui`）需携带请求头：`X-API-Key: <key>`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（公开）|
| GET | `/ui` | WebUI 管理界面（公开）|
| GET | `/get?country=US` | 随机返回一个可用代理 |
| GET | `/list?limit=100` | 返回代理列表（按延迟排序）|
| GET | `/stats` | 池统计信息 |
| POST | `/refresh` | 手动触发刷新 |
| GET | `/test-proxy?proxy=host:port` | 测试指定代理 |
| POST | `/add-proxy` | 手动添加 `{"proxy":"host:port","country":"CN"}` |
| POST | `/remove-proxy` | 删除代理 `{"proxy":"host:port"}` |
| GET | `/config` | 获取运行配置 |
| POST | `/config` | 修改并持久化运行配置 |

### 使用示例

```bash
curl -H "X-API-Key: your-key" http://localhost:8318/get
```

```python
import requests
info = requests.get("http://host:8318/get", headers={"X-API-Key": "your-key"}).json()
proxies = {"http": f"http://{info['proxy']}", "https": f"http://{info['proxy']}"}
resp = requests.get("https://example.com", proxies=proxies, timeout=10)
```

## 可配置项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `refresh_interval` | 600 | 自动刷新间隔（秒）|
| `max_workers` | 100 | 并发测试线程数 |
| `timeout` | 8 | 单代理测试超时（秒）|
| `test_url` | api.ipify.org | 测试目标 URL |

环境变量（优先级高于配置文件）：`PROXY_API_KEY` `REFRESH_INTERVAL` `MAX_WORKERS` `PROXY_TIMEOUT` `TEST_URL`
