#!/usr/bin/env python3
"""
Efficio Hub - Local Proxy & Web Server
Solves browser CORS issues by proxying Zoho CRM & Zoho Desk REST API calls server-side.
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import json
import os
import sys
import ssl

# Bypass SSL cert verify issues on local macOS Python
ssl_context = ssl._create_unverified_context()

PORT = int(os.environ.get("PORT", 8123))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Default Zoho OAuth Credentials (can be overridden via Environment Variables)
ZOHO_CONFIG = {
    "api_domain": os.environ.get("ZOHO_API_DOMAIN", "https://www.zohoapis.com"),
    "desk_domain": os.environ.get("ZOHO_DESK_DOMAIN", "https://desk.zoho.com"),
    "accounts_domain": os.environ.get("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.com"),
    "access_token": os.environ.get("ZOHO_ACCESS_TOKEN", "1000.ca1296e19da253b83bd0e08af38328da.737d508eaf67fd0d0e26ccf486117d73"),
    "refresh_token": os.environ.get("ZOHO_REFRESH_TOKEN", "1000.73523f2b29c511168f1649d1d3c5a197.4b040af68d3595c99ba8a6b17ab208e4"),
    "client_id": os.environ.get("ZOHO_CLIENT_ID", ""),
    "client_secret": os.environ.get("ZOHO_CLIENT_SECRET", "")
}

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
        req = urllib.request.Request(url, headers={
            "Authorization": f"Zoho-oauthtoken {ZOHO_CONFIG['access_token']}",
            "Content-Type": "application/json"
        })

        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                body = response.read()
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

        req = urllib.request.Request(url, data=post_body, headers={
            "Authorization": f"Zoho-oauthtoken {ZOHO_CONFIG['access_token']}",
            "Content-Type": "application/json"
        }, method="POST")

        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                body = response.read()
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
        req = urllib.request.Request(url, headers={
            "Authorization": f"Zoho-oauthtoken {ZOHO_CONFIG['access_token']}"
        })

        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                body = response.read()
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
        data = json.loads(post_body.decode("utf-8")) if content_len > 0 else {}

        client_id = data.get("client_id", ZOHO_CONFIG["client_id"])
        client_secret = data.get("client_secret", ZOHO_CONFIG["client_secret"])
        refresh_token = data.get("refresh_token", ZOHO_CONFIG["refresh_token"])

        if not client_id or not client_secret:
            self._set_cors_headers(400)
            self.wfile.write(json.dumps({"error": "client_id and client_secret required to auto-refresh token"}).encode())
            return

        refresh_url = f"{ZOHO_CONFIG['accounts_domain']}/oauth/v2/token?refresh_token={refresh_token}&client_id={client_id}&client_secret={client_secret}&grant_type=refresh_token"
        req = urllib.request.Request(refresh_url, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "access_token" in result:
                    ZOHO_CONFIG["access_token"] = result["access_token"]
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(result).encode())
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
