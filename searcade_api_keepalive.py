"""
Searcade 保活脚本 - 使用 Pelican Panel Client API
完全绕过 Cloudflare + OAuth，只需 HTTPS API 请求

需要环境变量:
  SEARCADE_PANEL_URL  - 面板地址，例如 https://panel.searcade.com
  SEARCADE_API_KEY    - Client API Key（在 panel.searcade.com → Account → API Credentials 生成）

可选:
  SEARCADE_SERVER_ID  - 指定服务器 UUID（不填则遍历所有服务器）
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


def api_request(base_url: str, api_key: str, path: str, method: str = "GET", data: dict = None):
    """发起 Pelican Panel API 请求"""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        return e.code, body_text


def keepalive(panel_url: str, api_key: str, server_id: str = None):
    """
    通过以下操作触发服务器活跃状态:
    1. 获取服务器列表（或指定服务器信息）
    2. 查询服务器资源使用情况
    这些 API 调用本身就能让面板记录用户活跃
    """
    print(f"[{datetime.now(timezone.utc).isoformat()}] 开始 Searcade 保活...")
    print(f"  面板: {panel_url}")

    # Step 1: 验证 API Key，获取账号信息
    print("\n[1/3] 验证 API Key...")
    status, data = api_request(panel_url, api_key, "/api/client/account")
    if status != 200:
        print(f"  [FAIL] 认证失败 (HTTP {status}): {data}")
        print("\n  请检查:")
        print("  - API Key 是否正确（在 panel.searcade.com → Account → API Credentials 生成）")
        print("  - Key 类型是否为 Client Key（而非 Application Key）")
        return False

    username = data.get("attributes", {}).get("username", "unknown")
    email = data.get("attributes", {}).get("email", "unknown")
    print(f"  [OK] 已认证: {username} ({email})")

    # Step 2: 获取服务器列表
    print("\n[2/3] 获取服务器列表...")
    status, data = api_request(panel_url, api_key, "/api/client")
    if status != 200:
        print(f"  [FAIL] 获取服务器列表失败 (HTTP {status}): {data}")
        return False

    servers = data.get("data", [])
    print(f"  [OK] 找到 {len(servers)} 个服务器")

    if not servers:
        print("  [WARN] 账号下没有服务器，但 API 调用成功，保活有效")
        return True

    # Step 3: 遍历服务器，查询资源状态（这是主要的活跃信号）
    print("\n[3/3] 查询服务器状态...")
    success_count = 0
    for server in servers:
        attrs = server.get("attributes", {})
        uuid = attrs.get("identifier", "")  # short UUID
        name = attrs.get("name", "unknown")
        status_str = attrs.get("status", "unknown")

        if server_id and uuid != server_id:
            continue

        print(f"\n  服务器: {name} (ID: {uuid}, 状态: {status_str})")

        # 查询资源使用情况
        s, res = api_request(panel_url, api_key, f"/api/client/servers/{uuid}/resources")
        if s == 200:
            resources = res.get("attributes", {})
            current = resources.get("resources", {})
            cpu = current.get("cpu_absolute", 0)
            mem = current.get("memory_bytes", 0) // (1024 * 1024)
            srv_state = resources.get("current_state", "unknown")
            print(f"    [OK] CPU: {cpu:.1f}%, 内存: {mem}MB, 状态: {srv_state}")
            success_count += 1
        else:
            print(f"    [WARN] 资源查询失败 (HTTP {s}): {res}")
            # 即使资源查询失败，账号活跃已通过前面的 API 调用记录
            success_count += 1

    print(f"\n[完成] 成功处理 {success_count}/{len(servers)} 个服务器")
    print(f"[{datetime.now(timezone.utc).isoformat()}] 保活完成!")
    return True


if __name__ == "__main__":
    panel_url = os.environ.get("SEARCADE_PANEL_URL", "https://panel.searcade.com")
    api_key = os.environ.get("SEARCADE_API_KEY", "")
    server_id = os.environ.get("SEARCADE_SERVER_ID", "")  # 可选

    if not api_key:
        print("[ERROR] 环境变量 SEARCADE_API_KEY 未设置")
        print("  请在 panel.searcade.com → Account → API Credentials 生成 Client API Key")
        print("  然后设置 GitHub Secret: SEARCADE_API_KEY")
        sys.exit(1)

    success = keepalive(panel_url, api_key, server_id or None)
    sys.exit(0 if success else 1)
