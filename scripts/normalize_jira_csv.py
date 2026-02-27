#!/usr/bin/env python3
"""
Normaliza um CSV exportado do Jira para uso no dashboard (Looker Studio).
Seleciona colunas úteis, normaliza datas para ISO e gera um CSV limpo.
Uso: python normalize_jira_csv.py [arquivo_entrada.csv] [arquivo_saida.csv]
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path


# Colunas desejadas para o dashboard (ordem do output)
OUTPUT_COLUMNS = [
    "Summary",
    "Issue key",
    "Issue id",
    "Issue Type",
    "Status",
    "Project key",
    "Project name",
    "Priority",
    "Resolution",
    "Assignee",
    "Reporter",
    "Created",
    "Updated",
    "Resolved",
    "Due date",
    "Team Name",
    "Sprint",
    "Custom field (Produto)",
    "Status Category",
    "Status Category Changed",
]

# Formatos de data comuns no export Jira (locale PT-BR / EN)
DATE_FORMATS = [
    "%d/%b/%y %I:%M %p",      # 10/Dec/25 8:43 AM
    "%d/%b./%y %H:%M",       # 22/jan./26 10:04
    "%d/%b/%y %H:%M",        # 19/Dec/25 14:38
    "%Y-%m-%d %H:%M:%S.%f",  # 2025-12-10 11:44:34.17
    "%d/%b./%y %I:%M %p",
    "%d/%b/%y",
    "%Y-%m-%d",
]


def parse_date(value):
    """Tenta interpretar uma string como data e retorna ISO ou string vazia."""
    if not value or (isinstance(value, str) and not value.strip()):
        return ""
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # Última tentativa: só a parte antes de ponto ou espaço extra
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(value[:19], fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S") if " " in value else dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return value


def first_sprint_value(row_list, header):
    """Pega o primeiro valor não vazio entre colunas Sprint (múltiplas)."""
    for i, name in enumerate(header):
        if name == "Sprint" and i < len(row_list):
            val = row_list[i].strip() if row_list[i] else ""
            if val:
                return val
    return ""


def normalize_row(row_list, header, name_to_idx, date_columns):
    out = {}
    for col in OUTPUT_COLUMNS:
        if col == "Sprint":
            out[col] = first_sprint_value(row_list, header)
            continue
        idx = name_to_idx.get(col)
        if idx is None:
            out[col] = ""
            continue
        val = row_list[idx] if idx < len(row_list) else ""
        if not isinstance(val, str):
            val = "" if val is None else str(val)
        if col in date_columns:
            val = parse_date(val)
        out[col] = val
    return out


def read_csv_headers(f):
    """Lê primeira linha e retorna mapa nome -> índice (primeira ocorrência)."""
    reader = csv.reader(f)
    header = next(reader)
    name_to_idx = {}
    for i, name in enumerate(header):
        if name not in name_to_idx:
            name_to_idx[name] = i
    return name_to_idx, header, reader


def main():
    parser = argparse.ArgumentParser(description="Normaliza CSV do Jira para o dashboard.")
    parser.add_argument("input", nargs="?", default="Jira - Jira.csv.csv", help="CSV de entrada")
    parser.add_argument("output", nargs="?", default="jira_tickets_clean.csv", help="CSV de saída")
    parser.add_argument("--encoding", default="utf-8", help="Encoding do arquivo de entrada")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.is_absolute():
        input_path = Path(__file__).resolve().parent.parent / input_path
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent.parent / output_path

    if not input_path.exists():
        print(f"Erro: arquivo não encontrado: {input_path}", file=sys.stderr)
        sys.exit(1)

    date_columns = {"Created", "Updated", "Resolved", "Due date", "Status Category Changed"}

    rows_out = []
    with open(input_path, "r", encoding=args.encoding, newline="") as f:
        name_to_idx, header, reader = read_csv_headers(f)
        for row_list in reader:
            if len(row_list) < len(header):
                row_list.extend([""] * (len(header) - len(row_list)))
            normalized = normalize_row(row_list, header, name_to_idx, date_columns)
            rows_out.append(normalized)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(rows_out)

    print(f"Escritos {len(rows_out)} registros em {output_path}")


if __name__ == "__main__":
    main()
