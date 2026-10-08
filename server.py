#!/usr/bin/env python3
"""
Efficio Hub - Local Proxy & Web Server
Solves browser CORS issues by proxying Zoho CRM & Zoho Desk REST API calls server-side.
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import sys
import ssl
import threading
import time

# Bypass SSL cert verify issues on local macOS Python
ssl_context = ssl._create_unverified_context()

PORT = int(os.environ.get("PORT", 8123))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Default Zoho OAuth Credentials (can be overridden via Environment Variables)
ZOHO_CONFIG = {
    "api_domain": os.environ.get("ZOHO_API_DOMAIN", "https://www.zohoapis.com"),
    "desk_domain": os.environ.get("ZOHO_DESK_DOMAIN", "https://desk.zoho.com"),
    "accounts_domain": os.environ.get("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.com"),
    "access_token": os.environ.get("ZOHO_ACCESS_TOKEN", "1000.d47c891102b3a79842b513d7c915f750.9438d855d33a4f673dd49e59171b5d92"),
    "refresh_token": os.environ.get("ZOHO_REFRESH_TOKEN", "1000.2b4ee406c82aa28886141177da5cd9d5.b793e8b513bcb02da9bf3bd3a8670fca"),
    "client_id": os.environ.get("ZOHO_CLIENT_ID", "1000.82FN6LDFUHETKSEQE7QLVIEHCSB7IO"),
    "client_secret": os.environ.get("ZOHO_CLIENT_SECRET", "935ff64a0d3ae30e4784f3f6f1a58eb972e54528c8")
}
ZOHO_TOKEN_LOCK = threading.Lock()
ZOHO_ACCESS_TOKEN_EXPIRES_AT = None


def refresh_access_token(client_id=None, client_secret=None, refresh_token=None):
    """Exchange the configured refresh token for a fresh Zoho access token."""
    global ZOHO_ACCESS_TOKEN_EXPIRES_AT

    with ZOHO_TOKEN_LOCK:
        client_id = client_id or ZOHO_CONFIG["client_id"]
        client_secret = client_secret or ZOHO_CONFIG["client_secret"]
        refresh_token = refresh_token or ZOHO_CONFIG["refresh_token"]
        if not client_id or not client_secret or not refresh_token:
            raise ValueError("Zoho client ID, client secret, and refresh token are required")

        form_data = urllib.parse.urlencode({
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ZOHO_CONFIG['accounts_domain']}/oauth/v2/token",
            data=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=ssl_context) as response:
            result = json.loads(response.read().decode("utf-8"))

        new_access_token = result.get("access_token")
        if not new_access_token:
            raise RuntimeError(
                f"Zoho did not return an access token: {result.get('error', 'unknown OAuth error')}"
            )

        ZOHO_CONFIG["access_token"] = new_access_token
        if result.get("refresh_token"):
            ZOHO_CONFIG["refresh_token"] = result["refresh_token"]
        expires_in = result.get("expires_in")
        ZOHO_ACCESS_TOKEN_EXPIRES_AT = (
            time.time() + int(expires_in) if expires_in is not None else None
        )
        return result


def zoho_request(url, method="GET", data=None, headers=None):
    """Make a Zoho request, refreshing and retrying once for an expired token."""
    if (
        ZOHO_ACCESS_TOKEN_EXPIRES_AT is not None
        and time.time() >= ZOHO_ACCESS_TOKEN_EXPIRES_AT - 60
    ):
        refresh_access_token()

    def make_request():
        request_headers = dict(headers or {})
        request_headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_CONFIG['access_token']}"
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        return urllib.request.urlopen(request, context=ssl_context)

    try:
        with make_request() as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        error.close()

    refresh_access_token()
    with make_request() as response:
        return response.read()

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def _set_cors_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200)

    def do_GET(self):
        # 0. Route root URL '/' directly to webform.html
        if self.path == "/" or self.path == "":
            self.path = "/webform.html"

        # 1. API: Fetch active CRM users
        if self.path.startswith("/api/users"):
            self.handle_get_users()
            return

        # 2. API: Fetch Desk ticket
        if self.path.startswith("/api/desk/ticket/"):
            ticket_id = self.path.split("/")[-1].split("?")[0]
            self.handle_get_desk_ticket(ticket_id)
            return

        # 3. Static Files (webform.html, index.html, etc.)
        super().do_GET()

    def do_POST(self):
        # 1. API: Create Lead in Zoho CRM
        if self.path == "/api/leads" or self.path == "/api/leads/":
            self.handle_create_lead()
            return

        # 2. API: Update Token / Settings
        if self.path == "/api/config":
            self.handle_update_config()
            return

        # 3. API: Refresh Access Token
        if self.path == "/api/refresh-token":
            self.handle_refresh_token()
            return

        self._set_cors_headers(404)
        self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode())

    # --- API Handlers ---

    def handle_get_users(self):
        """Proxy GET /crm/v6/users?type=ActiveUsers"""
        url = f"{ZOHO_CONFIG['api_domain']}/crm/v6/users?type=ActiveUsers"

        try:
            body = zoho_request(url, headers={"Content-Type": "application/json"})
            data = json.loads(body.decode("utf-8"))
                
            # Filter strictly active users and exclude deleted
            active_users = [
                {
                    "id": u.get("id"),
                    "full_name": u.get("full_name"),
                    "email": u.get("email"),
                    "role": u.get("role", {}).get("name") if isinstance(u.get("role"), dict) else u.get("role"),
                    "profile": u.get("profile", {}).get("name") if isinstance(u.get("profile"), dict) else u.get("profile"),
                    "status": u.get("status")
                }
                for u in data.get("users", [])
                if u.get("status") == "active"
            ]

            # Sort by full_name
            active_users.sort(key=lambda x: x["full_name"] or "")

            cleaned_response = json.dumps({"users": active_users})
            self._set_cors_headers(200)
            self.wfile.write(cleaned_response.encode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[Error] Zoho CRM Users API returned {e.code}: {err_body}")
            self._set_cors_headers(e.code)
            self.wfile.write(err_body.encode())
        except Exception as e:
            print(f"[Error] Failed to connect to Zoho: {e}")
            self._set_cors_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_create_lead(self):
        """Proxy POST /crm/v6/Leads"""
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)

        url = f"{ZOHO_CONFIG['api_domain']}/crm/v6/Leads"
        print(f"[Lead Submission] Sending payload to {url}: {post_body.decode('utf-8')[:200]}...")

        try:
            body = zoho_request(
                url,
                method="POST",
                data=post_body,
                headers={"Content-Type": "application/json"},
            )
            print(f"[Success] Zoho Response: {body.decode('utf-8')}")
            self._set_cors_headers(200)
            self.wfile.write(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[HTTP Error] Zoho CRM returned status {e.code}: {err_body}")
            self._set_cors_headers(e.code)
            self.wfile.write(err_body.encode())
        except Exception as e:
            print(f"[Server Error] {e}")
            self._set_cors_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_get_desk_ticket(self, ticket_id):
        """Proxy GET /api/v1/tickets/{ticket_id}"""
        url = f"{ZOHO_CONFIG['desk_domain']}/api/v1/tickets/{ticket_id}"

        try:
            body = zoho_request(url)
            self._set_cors_headers(200)
            self.wfile.write(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            self._set_cors_headers(e.code)
            self.wfile.write(err_body.encode())
        except Exception as e:
            self._set_cors_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_update_config(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)
        try:
            data = json.loads(post_body.decode("utf-8"))
            if "access_token" in data and data["access_token"]:
                ZOHO_CONFIG["access_token"] = data["access_token"]
            if "refresh_token" in data and data["refresh_token"]:
                ZOHO_CONFIG["refresh_token"] = data["refresh_token"]
            if "api_domain" in data and data["api_domain"]:
                ZOHO_CONFIG["api_domain"] = data["api_domain"]
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({"status": "updated", "config": {
                "api_domain": ZOHO_CONFIG["api_domain"],
                "token_preview": ZOHO_CONFIG["access_token"][:15] + "..."
            }}).encode())
        except Exception as e:
            self._set_cors_headers(400)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_refresh_token(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)
        try:
            data = json.loads(post_body.decode("utf-8")) if content_len > 0 else {}
            result = refresh_access_token(
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
                refresh_token=data.get("refresh_token"),
            )
            self._set_cors_headers(200)
            self.wfile.write(json.dumps(result).encode())
        except ValueError as e:
            self._set_cors_headers(400)
            self.wfile.write(json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self._set_cors_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProxyHTTPRequestHandler) as httpd:
        print(f"🚀 Efficio Hub Server running at http://localhost:{PORT}/webform.html")
        print(f"📡 CORS Proxy Endpoints active: /api/users, /api/leads, /api/desk/ticket/:id")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.server_close()
