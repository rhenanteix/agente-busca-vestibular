#!/usr/bin/env python3
"""Agente que busca datas de vestibulares no Vale do Ribeira (SP).

Uso:
    export ANTHROPIC_API_KEY=sk-ant-...
    python agente_vestibular.py

Gera: vestibulares.json, vestibulares.csv e index.html
"""
import csv
import json
import os
import re
import sys
from datetime import datetime

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

# Cidades do Vale do Ribeira (SP) usadas na descoberta de novas instituições
CIDADES = [
    "Registro", "Iguape", "Cajati", "Pariquera-Açu", "Eldorado", "Jacupiranga",
    "Miracatu", "Juquiá", "Sete Barras", "Ilha Comprida", "Cananéia", "Apiaí",
    "Itariri", "Pedro de Toledo", "Barra do Turvo", "Juquitiba", "Tapiraí",
]

# Lista inicial (edite à vontade). O modo de descoberta abaixo completa a lista.
INSTITUICOES = [
    "UNESP - Campus Experimental de Registro",
    "IFSP - Campus Registro",
    "IFSP - Campus Cajati",
    "UNIVESP - polos do Vale do Ribeira",
]


def extrair_json(texto: str):
    """Extrai o primeiro bloco JSON (lista ou objeto) de um texto."""
    texto = re.sub(r"```json|```", "", texto)
    m = re.search(r"(\[.*\]|\{.*\})", texto, re.S)
    if not m:
        raise ValueError("Nenhum JSON encontrado na resposta")
    return json.loads(m.group(1))


def perguntar(prompt: str, max_searches: int = 6):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
        messages=[{"role": "user", "content": prompt}],
    )
    texto = "".join(b.text for b in resp.content if b.type == "text")
    return extrair_json(texto)


def descobrir_instituicoes():
    """Pede ao Claude para listar instituições de ensino superior na região."""
    prompt = f"""Pesquise na web instituições de ensino superior (públicas e privadas,
presenciais ou com polo/campus) que tenham unidade nestas cidades do Vale do Ribeira (SP):
{", ".join(CIDADES)}.
Responda SOMENTE com uma lista JSON de strings no formato "Instituição - unidade/cidade".
Inclua apenas instituições que você confirmou em fontes na web."""
    try:
        return perguntar(prompt, max_searches=8)
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] descoberta falhou: {e}", file=sys.stderr)
        return []


def buscar_datas(instituicao: str):
    hoje = datetime.now().strftime("%d/%m/%Y")
    prompt = f"""Hoje é {hoje}. Pesquise no site oficial (prioridade) da instituição:
"{instituicao}" as informações do PRÓXIMO(S) vestibular/processo seletivo de graduação
(inclui Enem/SiSU/Vunesp/ingresso por nota só se for o formato oficial de entrada).

Responda SOMENTE com uma lista JSON, onde cada item tem as chaves:
"instituicao", "processo" (nome), "inscricao_inicio", "inscricao_fim", "data_prova",
"resultado", "url_fonte", "observacoes".
Use datas no formato AAAA-MM-DD; se não souber, use null. Não invente datas:
se não encontrar, devolva um item com "observacoes": "não encontrado"."""
    try:
        itens = perguntar(prompt)
        return itens if isinstance(itens, list) else [itens]
    except Exception as e:  # noqa: BLE001
        print(f"[erro] {instituicao}: {e}", file=sys.stderr)
        return [{"instituicao": instituicao, "observacoes": f"falha na busca: {e}"}]


CAMPOS = ["instituicao", "processo", "inscricao_inicio", "inscricao_fim",
          "data_prova", "resultado", "url_fonte", "observacoes"]


def salvar(registros):
    atualizado = datetime.now().strftime("%d/%m/%Y %H:%M")
    with open("vestibulares.json", "w", encoding="utf-8") as f:
        json.dump({"atualizado_em": atualizado, "itens": registros}, f, ensure_ascii=False, indent=2)

    with open("vestibulares.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(registros)

    linhas = "".join(
        "<tr>" + "".join(
            f"<td>{(f'<a href=\"{r.get(c)}\">fonte</a>' if c == 'url_fonte' and r.get(c) else (r.get(c) or '—'))}</td>"
            for c in CAMPOS
        ) + "</tr>"
        for r in registros
    )
    cab = "".join(f"<th>{c.replace('_', ' ').title()}</th>" for c in CAMPOS)
    html = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Vestibulares - Vale do Ribeira</title>
<style>body{{font-family:system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:.4rem;font-size:.9rem}}th{{background:#f3f3f3}}</style>
<h1>Vestibulares - Vale do Ribeira</h1>
<p>Atualizado em {atualizado}. Sempre confirme no edital oficial.</p>
<table><tr>{cab}</tr>{linhas}</table></html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)


def main():
    nomes = list(INSTITUICOES)
    if os.environ.get("DESCOBRIR", "1") == "1":
        for n in descobrir_instituicoes():
            if isinstance(n, str) and n not in nomes:
                nomes.append(n)

    registros = []
    for n in nomes:
        print(f"Buscando: {n}")
        registros.extend(buscar_datas(n))
    salvar(registros)
    print(f"Pronto: {len(registros)} registros.")


if __name__ == "__main__":
    main()
