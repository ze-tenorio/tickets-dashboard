#!/usr/bin/env python3
"""
Sincroniza issues do Jira com o Google Sheets (mesmo esquema do CSV limpo).
Uso: defina variáveis de ambiente e execute o script.
Em CI (GitHub Actions), use secrets para JIRA_* e GOOGLE_*.
"""
import os
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import requests
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError as e:
    print("Instale as dependências: pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(1) from e

# Mesmo esquema do normalize_jira_csv.py para o Looker Studio
OUTPUT_COLUMNS = [
    "Summary", "Issue key", "Issue id", "Issue Type", "Status",
    "Project key", "Project name", "Priority", "Resolution",
    "Assignee", "Reporter", "Created", "Updated", "Resolved", "Due date",
    "Team Name", "Sprint", "Custom field (Produto)", "Status Category", "Status Category Changed",
]


def jira_headers():
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        raise SystemExit("Defina JIRA_EMAIL e JIRA_API_TOKEN.")
    return {"Accept": "application/json", "Content-Type": "application/json"}


def jira_auth():
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    return (email, token) if email and token else None


def get_jira_base():
    base = os.environ.get("JIRA_BASE_URL", "https://starbemapp.atlassian.net").rstrip("/")
    return base


def fetch_jira_fields(base, auth):
    """Mapeia id do campo -> nome (para custom fields)."""
    r = requests.get(
        f"{base}/rest/api/3/field",
        auth=auth,
        headers=jira_headers(),
        timeout=30,
    )
    r.raise_for_status()
    by_id = {}
    for f in r.json():
        by_id[f["id"]] = f.get("name") or f["id"]
    return by_id


def fetch_all_issues(base, auth, jql=None):
    """Busca todas as issues via paginação."""
    if jql is None:
        jql = os.environ.get("JIRA_JQL", "order by created DESC")
    start = 0
    total = None
    issues = []
    while total is None or start < total:
        r = requests.get(
            f"{base}/rest/api/3/search",
            auth=auth,
            headers=jira_headers(),
            params={"jql": jql, "startAt": start, "maxResults": 100, "expand": "names"},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        total = data["total"]
        issues.extend(data["issues"])
        start += len(data["issues"])
        if start >= total:
            break
    return issues


def format_jira_date(iso_str):
    """Jira retorna ISO; mantemos formato consistente com o CSV limpo."""
    if not iso_str:
        return ""
    try:
        # Jira: 2026-01-22T10:04:00.000-0300
        from datetime import datetime
        s = iso_str.split(".")[0].replace("Z", "+00:00")
        if "+" in s or "-" in s[-6:]:
            dt = datetime.fromisoformat(s.replace("+00:00", "").split("-03")[0])
        else:
            dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str


def issue_to_row(issue, field_names_by_id):
    """Converte uma issue da API para uma linha (dict) no esquema do dashboard."""
    f = issue.get("fields") or {}
    # Resolução pode ser objeto
    res = f.get("resolution")
    resolution = res.get("name", "") if isinstance(res, dict) else (res or "")

    # Assignee / Reporter
    assignee = ""
    if f.get("assignee"):
        assignee = f["assignee"].get("displayName") or f["assignee"].get("emailAddress") or ""
    reporter = ""
    if f.get("reporter"):
        reporter = f["reporter"].get("displayName") or f["reporter"].get("emailAddress") or ""

    # Status category
    status = f.get("status") or {}
    status_category = ""
    if isinstance(status, dict):
        sc = status.get("statusCategory") or {}
        status_category = sc.get("name", "") if isinstance(sc, dict) else ""

    # Custom fields: procurar por nome conhecido
    team_name = ""
    sprint = ""
    produto = ""
    for key, value in f.items():
        if not key.startswith("customfield_"):
            continue
        name = field_names_by_id.get(key, key)
        if value is None:
            continue
        if name == "Team Name":
            if isinstance(value, dict):
                team_name = value.get("name") or value.get("value") or str(value)
            else:
                team_name = str(value)
        elif name == "Sprint":
            if isinstance(value, (list, tuple)) and value:
                sprint = value[0] if isinstance(value[0], str) else value[0].get("name", str(value[0]))
            elif isinstance(value, str):
                sprint = value
            else:
                sprint = str(value)
        elif name == "Custom field (Produto)" or name == "Produto":
            if isinstance(value, dict):
                produto = value.get("value") or value.get("name") or str(value)
            else:
                produto = str(value)

    return {
        "Summary": (f.get("summary") or "").strip(),
        "Issue key": issue.get("key", ""),
        "Issue id": str(issue.get("id", "")),
        "Issue Type": (f.get("issuetype") or {}).get("name", "") if isinstance(f.get("issuetype"), dict) else str(f.get("issuetype", "")),
        "Status": status.get("name", "") if isinstance(status, dict) else str(status),
        "Project key": (f.get("project") or {}).get("key", "") if isinstance(f.get("project"), dict) else "",
        "Project name": (f.get("project") or {}).get("name", "") if isinstance(f.get("project"), dict) else "",
        "Priority": (f.get("priority") or {}).get("name", "") if isinstance(f.get("priority"), dict) else "",
        "Resolution": resolution,
        "Assignee": assignee,
        "Reporter": reporter,
        "Created": format_jira_date(f.get("created")),
        "Updated": format_jira_date(f.get("updated")),
        "Resolved": format_jira_date(f.get("resolutiondate")),
        "Due date": format_jira_date(f.get("duedate")),
        "Team Name": team_name,
        "Sprint": sprint,
        "Custom field (Produto)": produto,
        "Status Category": status_category,
        "Status Category Changed": format_jira_date(f.get("statusCategoryChangedDate") or ""),
    }


def get_sheets_service():
    """Credenciais: GOOGLE_APPLICATION_CREDENTIALS (path) ou GOOGLE_SERVICE_ACCOUNT_JSON (string)."""
    json_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if json_path and Path(json_path).exists():
        creds = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    else:
        import json
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not raw:
            raise SystemExit(
                "Defina GOOGLE_APPLICATION_CREDENTIALS (caminho do JSON) ou "
                "GOOGLE_SERVICE_ACCOUNT_JSON (conteúdo do JSON)."
            )
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    return build("sheets", "v4", credentials=creds)


def write_to_sheet(rows):
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SystemExit("Defina GOOGLE_SHEET_ID (ID da planilha na URL).")
    sheet_name = os.environ.get("GOOGLE_SHEET_TAB", "Tickets")

    service = get_sheets_service()
    body = {
        "values": [OUTPUT_COLUMNS] + [[row.get(c, "") for c in OUTPUT_COLUMNS] for row in rows],
    }
    # Limpa colunas A até T (20 colunas) e escreve (full refresh)
    clear_range = f"'{sheet_name}'!A:T"
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=clear_range,
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{sheet_name}'!A1",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()
    print(f"Atualizadas {len(rows)} linhas na aba '{sheet_name}'.")


def main():
    base = get_jira_base()
    auth = jira_auth()
    if not auth:
        raise SystemExit("JIRA_EMAIL e JIRA_API_TOKEN são obrigatórios.")

    field_names = fetch_jira_fields(base, auth)
    issues = fetch_all_issues(base, auth)
    rows = [issue_to_row(i, field_names) for i in issues]

    write_to_sheet(rows)


if __name__ == "__main__":
    main()
