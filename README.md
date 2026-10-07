# Efficio Hub - Zoho CRM & Zoho Desk Lead Conversion Engine

A modern, high-performance web application for converting Zoho Desk tickets and capturing Leads into **Zoho CRM** with dynamic **Lead Owner** lookup, field visibility layout rules, and CORS-free backend proxying.

---

## 🚀 Features

- **Dynamic Lead Owner Lookup**: Queries `GET /crm/v6/users?type=ActiveUsers` from Zoho CRM and populates a real-time selectable user roster.
- **Dual Owner Assignment**: Guarantees lead assignment by mapping both the standard CRM `Owner` lookup and custom `owner1` UserLookup fields.
- **Stage Visibility Rules (`WHEN Lead Stage`)**:
  - `New`: Displays initial qualification and follow-up fields (`Next_Follow_up_Date`, `Priority`).
  - `Proposal`: Dynamically reveals financial and product fields (`Estimated_Deal_Value`, `Total_Sales_Price`, `Expected_Close_Date`, `Expected_Sales`, `Sale_Product`, `VAT_TRN`).
  - `In Progress`: Displays progress and schedule fields (`Next_Follow_up_Date`, `Expected_Close_Date`).
  - `Converted`: Displays deal total, registration, and converted details.
- **Address Card with Country/State Hierarchy**:
  - Dynamic cascading dropdowns for GCC / Middle East & International states (UAE, Saudi Arabia, Oman, Qatar, Kuwait, Bahrain, India, US, UK, etc.).
  - Coordinates tracking (`Latitude` and `Longitude`).
- **Zoho Desk Ticket Pre-fill**:
  - Enter a Ticket ID to auto-populate customer name, email, mobile, company, and subject notes.
- **Built-in Python Proxy Server (`server.py`)**:
  - Eliminates browser CORS issues with native endpoints (`/api/users`, `/api/leads`, `/api/desk/ticket/:id`).
  - No external pip dependencies required (runs with standard Python 3).

---

## 🛠️ Tech Stack

- **Frontend**: Vanilla HTML5, CSS3 (Zoho CRM Design System), Modern Vanilla JavaScript (ES6+).
- **Backend / Proxy**: Python 3 standard library (`http.server`, `urllib`, `ssl`, `json`).
- **API Integration**: Zoho CRM API v6 & Zoho Desk API v1.

---

## 📦 Local Installation & Run

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/efficio-hub.git
   cd efficio-hub
   ```

2. Start the local server:
   ```bash
   python3 server.py
   ```

3. Open in your browser:
   ```text
   http://localhost:8123/webform.html
   ```

---

## 🌐 Deployment Options

### Option 1: Render / Railway / Python Cloud Host (Recommended)
1. Push this repository to GitHub.
2. Link your repository to [Render](https://render.com) or [Railway](https://railway.app).
3. Set the start command:
   ```bash
   python3 server.py
   ```
4. Set the environment variable `PORT` if required.

### Option 2: VPS / EC2 / Server
1. Clone the repo on your server.
2. Run with `systemd` or `pm2`:
   ```bash
   pm2 start server.py --name "efficio-hub" --interpreter python3
   ```

---

## 🔐 Zoho OAuth Scopes Required

When generating tokens in [Zoho API Console](https://api-console.zoho.com):
```text
ZohoCRM.modules.ALL,ZohoCRM.users.ALL,ZohoCRM.settings.ALL,Desk.tickets.ALL,Desk.contacts.ALL,Desk.basic.ALL,Desk.settings.ALL
```
