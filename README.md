# Agenda Vale do Ribeira (v2)

Coleta automática de **datas, editais, isenções de taxa e eventos**: ENEM/Sisu/ProUni/Fies, vestibulares
(Fuvest, Unicamp, Unesp, Etec, Fatec, IFSP, Univesp), faculdades da região (IFSP Registro, Unesp Registro, UNIVR/Unisepe),
prefeituras e notícias dos 23 municípios do Vale (via Google News RSS).

## Rodar
    pip install -r requirements.txt
    python crawler.py --check          # 1º passo: quais URLs respondem e quantas datas/links cada uma rendeu
    python crawler.py                  # coleta tudo -> pasta docs/
    python crawler.py --sem-noticias   # só fontes diretas (mais rápido)

Abra `docs/index.html` no navegador: painel com busca, filtro por nível/tipo, aba de editais/links e alerta de prazos.

## O que sai em docs/
| arquivo | conteúdo |
|---|---|
| index.html | painel (datas + editais e links) |
| eventos.ics | importe no Google Agenda / Apple / Outlook |
| eventos.csv / .json | todas as datas (tipo: isenção, inscrição, prova, resultado, matrícula, edital, acadêmico, evento) |
| documentos.csv / .json | editais (PDF), páginas de edital/calendário e notícias encontradas |
| prazos_proximos.txt | inscrições/isenções/matrículas conferidas que fecham em até 7 dias |
| novos.txt | o que apareceu desde a última execução |

## Automatizar (grátis)
1. Suba a pasta para um repositório no GitHub.
2. O workflow `.github/workflows/crawler.yml` roda todo dia às 06h e atualiza `docs/`.
3. Settings > Pages > "Deploy from a branch" > pasta `/docs`: o painel e o `.ics` ganham URL pública
   (assine `https://SEU-USUARIO.github.io/REPO/eventos.ics` no Google Agenda e ele se atualiza sozinho).
4. Avisos no celular: crie um bot no Telegram (@BotFather) e salve os secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
Alternativa local: `crontab -e` -> `0 6 * * * cd /caminho && python3 crawler.py`

## Personalizar
- `fontes.json`: adicione sites (copie uma linha), mude `categoria` (`educacao`, `faculdade` = + eventos/calendário acadêmico, `local`).
  `municipios` e `gnews_*` geram as buscas automáticas; edite os termos à vontade.
- `eventos_base.csv`: datas já conferidas. Linhas com `PREVISÃO` na coluna `obs` são estimativas (aparecem em amarelo).

## Limites (leia)
- Datas lidas de texto podem errar contexto: **confira no edital** antes de agir. Só `conferido` é manual; `automático` não.
- Google News traz só manchete: serve para descobrir edital/notícia nova (aba "Editais e links") e datas que estejam no título.
- Sites que carregam tudo por JavaScript, ou publicam só imagem/banner, não são lidos (precisaria Playwright/OCR).
- Respeita robots.txt (exceto RSS do Google News) e espera 1s entre requisições; defina `CONTATO` com seu e-mail.
