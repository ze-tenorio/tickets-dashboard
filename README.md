# Dashboard de tickets Jira (Looker Studio + sync automático)

Projeto para análise de volume de tickets Jira: **dashboard local** (Streamlit), normalização do CSV exportado, opção de dashboard no **Looker Studio** e sincronização automática com o Jira via **Google Sheets**.

## Dashboard local (análise com gráficos)

O dashboard interativo usa os dados do `jira_tickets_clean.csv` e mostra KPIs, volume ao longo do tempo, distribuição por status, prioridade, responsáveis e produto/área.

**Opção 1 – Script (Windows)**  
Dê dois cliques em `run_dashboard.bat`. O terminal vai abrir e o navegador pode abrir sozinho em **http://localhost:8501**. Se não abrir, acesse esse endereço manualmente.

**Opção 2 – Terminal**

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

Depois abra no navegador: **http://localhost:8501**. Use os filtros na barra lateral para refinar a análise.

Se a página não carregar, confira se nenhum outro programa está usando a porta 8501 e tente de novo.

### Como atualizar a base no dashboard

O dashboard lê sempre o **`jira_tickets_clean.csv`**. Para atualizar (status, prioridade, etc.):

1. **Edite o `jira_tickets_clean.csv`** na raiz do projeto (Excel, VS Code, etc.).
2. **Local:** recarregue a página do dashboard (F5) ou reinicie o `streamlit run app.py`.
3. **Streamlit Cloud:** faça commit do `jira_tickets_clean.csv` e push para o GitHub; o app vai redeployar sozinho e usar o arquivo novo. Não precisa rodar nenhum script.

Se você não tiver o CSV limpo e tiver só o export bruto do Jira, coloque o **`Jira.csv`** na raiz e rode uma vez:  
`python scripts/normalize_jira_csv.py Jira.csv jira_tickets_clean.csv` — isso gera o `jira_tickets_clean.csv` para você editar ou subir.

## Estrutura

- **`app.py`** – Dashboard Streamlit (gráficos e tabela).
- **`scripts/normalize_jira_csv.py`** – Lê o CSV exportado do Jira, mantém só as colunas usadas no dashboard, normaliza datas para ISO e gera um CSV limpo.
- **`scripts/sync_jira_to_sheet.py`** – Busca issues na API do Jira e atualiza uma planilha no Google Sheets (mesmo esquema do CSV limpo).
- **`.github/workflows/sync-jira.yml`** – Workflow que roda o sync em cron (diário) ou manualmente.

## Pré-requisitos

- Python 3.10+
- Para sync: conta Jira Cloud com API token e Google Cloud com Service Account com acesso à API do Google Sheets.

## 1. Normalizar o CSV (Fase 1 – dashboard a partir do CSV)

Gera um CSV enxuto para importar no Google Sheets e conectar ao Looker Studio:

```bash
pip install -r requirements.txt   # opcional para o normalize (usa só stdlib)
python scripts/normalize_jira_csv.py "Jira - Jira.csv.csv" jira_tickets_clean.csv
```

- **Entrada**: caminho do CSV exportado do Jira (padrão: `Jira - Jira.csv.csv`).
- **Saída**: `jira_tickets_clean.csv` (padrão) na raiz do projeto.

Próximos passos manuais:

1. Criar uma planilha no [Google Sheets](https://sheets.google.com) e importar o `jira_tickets_clean.csv` (ou colar o conteúdo).
2. Criar um relatório no [Looker Studio](https://lookerstudio.google.com), adicionar fonte de dados “Google Sheets” e selecionar essa planilha.
3. Ajustar tipos dos campos (datas como Data, etc.) e montar os painéis (volume por data, status, prioridade, assignee/equipe, etc.).

## 2. Sincronizar Jira → Google Sheets (Fase 2)

O script lê issues via **Jira Cloud REST API** e reescreve a aba configurada no Google Sheets (full refresh).

### Variáveis de ambiente

Copie `.env.example` para `.env` e preencha (nunca commite `.env`):

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `JIRA_BASE_URL` | Sim | Base da instância (ex.: `https://sua-empresa.atlassian.net`) |
| `JIRA_EMAIL` | Sim | Email da conta Atlassian |
| `JIRA_API_TOKEN` | Sim | [API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_JQL` | Não | JQL da busca (padrão: `order by created DESC`) |
| `GOOGLE_SHEET_ID` | Sim | ID da planilha (na URL: `/d/ESTE_ID/edit`) |
| `GOOGLE_SHEET_TAB` | Não | Nome da aba (padrão: `Tickets`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Sim* | Caminho do JSON da Service Account |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Sim* | Conteúdo do JSON (alternativa; útil em CI) |

\* Uma das duas: arquivo no disco ou JSON em variável.

### Google Sheets – Service Account

1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto (ou use um existente).
2. Ative a **Google Sheets API**.
3. Crie uma **Service Account**, baixe o JSON da chave.
4. Compartilhe a planilha com o email da service account (ex.: `...@...iam.gserviceaccount.com`) como **Editor**.

### Executar o sync localmente

```bash
pip install -r requirements.txt
set GOOGLE_APPLICATION_CREDENTIALS=.\caminho\para\service-account.json
# Defina também JIRA_* e GOOGLE_SHEET_ID (e opcionalmente GOOGLE_SHEET_TAB e JIRA_JQL)
python scripts/sync_jira_to_sheet.py
```

No Linux/macOS use `export` em vez de `set`.

## 3. Agendamento (GitHub Actions)

O workflow **Sync Jira to Google Sheets** está em `.github/workflows/sync-jira.yml`:

- **Agendado**: todo dia às 8h UTC (5h BRT).
- **Manual**: Actions → Sync Jira to Google Sheets → Run workflow.

Configure os **secrets** do repositório (Settings → Secrets and variables → Actions):

- `JIRA_BASE_URL`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (conteúdo do JSON da Service Account)

Opcionais:

- `JIRA_JQL` – JQL da busca.
- `GOOGLE_SHEET_TAB` – Nome da aba (padrão: `Tickets`).

Depois do sync, o Looker Studio que estiver conectado a essa planilha passa a refletir os dados atualizados (atualize o relatório ou use atualização automática conforme a configuração da fonte).

## Esquema dos dados (dashboard)

O CSV limpo e o sync usam as mesmas colunas:

- **Identificação**: Summary, Issue key, Issue id, Issue Type  
- **Status**: Status, Status Category, Resolution  
- **Prioridade**: Priority  
- **Pessoas**: Assignee, Reporter, Team Name  
- **Datas**: Created, Updated, Resolved, Due date, Status Category Changed  
- **Contexto**: Project key, Project name, Sprint, Custom field (Produto)

Isso permite manter um único relatório no Looker Studio tanto para o CSV importado manualmente quanto para a planilha alimentada pelo sync.
