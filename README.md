# Agenda Universitária - Vale do Ribeira

Coleta datas de **vestibulares, inscrições, isenção de taxa, matrículas, editais e eventos acadêmicos**
das instituições do Vale do Ribeira (IFSP Registro, Unesp Registro, UNIVR/Unisepe, prefeituras e notícias dos 23 municípios)
e dos programas **nacionais** (ENEM, Encceja, Sisu, ProUni, Fies). Vestibulares de fora da região (Fuvest, Unicamp, Etec...)
ficam desativados em `fontes.json` (`"ativo": false`).

## Rodar (Mac)
    cd agente-busca-vestibular
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    python crawler.py --reset --check     # testa as fontes ([OK] / [ERR])
    python crawler.py --sem-noticias      # coleta rápida (poucos minutos)
    python crawler.py                     # coleta completa (inclui Google News, ~10 min)
Depois é só `source venv/bin/activate` e `python crawler.py` nas próximas vezes. Abra `docs/index.html` para ver o painel.

## Para alimentar a agenda (ribeiraconnect.com.br/rota-universitaria/agenda)
Use **`docs/agenda_rota_universitaria.json`** (ou `.csv`). Campos de cada item:
`id, titulo, descricao, categoria, data_inicio, data_fim, instituicao, cidade, abrangencia (nacional|regional), link, status, atualizado_em`

`status`: **conferido** (verificado em fontes oficiais), **previsao** (estimativa, sem edital ainda) ou **automatico**
(lido do site; confira no edital antes de publicar). Sugestão: publique só `conferido` + `previsao` e revise os `automatico`.

Envio automático para o seu sistema: defina `WEBHOOK_URL` (e `WEBHOOK_TOKEN`, opcional) e o crawler faz um POST com o JSON toda vez que rodar.

## Outras saídas (docs/)
index.html (painel) · eventos.ics (calendário) · documentos.csv (editais/PDFs/notícias) · prazos_proximos.txt · novos.txt

## Automatizar (grátis)
Suba para o GitHub: `.github/workflows/crawler.yml` roda todo dia às 06h. Secrets opcionais: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WEBHOOK_URL`, `WEBHOOK_TOKEN`.

## Limites
- O crawler não foi testado nos sites reais; rode `--check` e ajuste URLs que derem `[ERR]` em `fontes.json`.
- Datas lidas de texto podem errar contexto: confira `automatico` no edital.
- Sites só com imagem/JavaScript pesado não são lidos.
