#!/usr/bin/env python3
"""
Agenda Vale do Ribeira v2 - datas, editais, isenções e eventos (ENEM, vestibulares, faculdades, prefeituras).

  python crawler.py --check            # testa cada fonte (status HTTP, datas e links achados)
  python crawler.py                    # coleta tudo e gera a pasta ./docs
  python crawler.py --only IFSP        # só fontes cujo nome contenha "IFSP"
  python crawler.py --sem-noticias     # pula as buscas no Google News (mais rápido)
  python crawler.py --all              # exporta também eventos passados

Saídas em ./docs: index.html (painel), eventos.csv/json/ics, documentos.csv/json (editais e links),
prazos_proximos.txt, novos.txt.  Telegram opcional: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
"""
import argparse, csv, datetime as dt, hashlib, io, json, os, re, sqlite3, time, unicodedata
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus, unquote

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).parent
SAIDA = BASE / "docs"
DB_PATH = BASE / "agenda.db"
UA = f"AgendaValeRibeiraBot/2.0 (+{os.getenv('CONTATO', 'uso educacional')})"
DELAY = float(os.getenv("DELAY", "1.0"))
MAX_PDF_MB = 25

MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
         "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8,
         "set": 9, "out": 10, "nov": 11, "dez": 12}


def sem_acento(s):
    s = s.replace("ª", "a").replace("º", "o")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    return re.sub(r"\s+", " ", sem_acento(s).lower()).strip()


# ----------------------------------------------------------------- classificação
RX = {
    "isencao": r"\b(isenc|isent|reducao d[ae] taxa|gratuidade)",
    "inscricao": r"\b(inscric|inscrev|inscreva|pagamento|cadastr)",
    "matricula": r"\b(matric|rematric)",
    "resultado": r"\b(resultad|classificac|convocac|chamada|gabarito|lista de espera|locais? de prova)",
    "prova": r"\b(provas?|exames?|vestibular|redacao|aplicacao|[12][oa] fase|primeira fase|segunda fase|[12][oa] dia|competencias especificas)\b",
    "edital": r"\b(edital|editais|manual do candidato|guia de provas)",
    "academico": r"\b(inicio das aulas|termino do semestre|fim do semestre|recesso|ferias|trancamento|calendario academico|aula inaugural|colacao de grau|formatura)",
    "evento": r"\b(festa|festival|feira|palestra|semana|congresso|workshop|oficina|seminario|encontro|exposicao|mostra|minicurso|capacitacao|audiencia|reuniao|jornada|simposio|show|rodeio|cavalgada|carnaval|aniversario|open day|portoes abertos|campeonato|torneio|corrida|desfile)\b",
}
RX = {k: re.compile(v) for k, v in RX.items()}
ORDEM = ["isencao", "inscricao", "matricula", "resultado", "prova", "edital", "academico", "evento"]
DOC_RX = re.compile(r"(edital|editais|calendario|processo seletivo|vestibular|isenc|inscric|manual do candidato|guia de provas|resultado|convocac|chamada|matricula|cronograma)")
SOCIAL = re.compile(r"(facebook|instagram|twitter|x\.com|youtube|whatsapp|linkedin|tiktok|mailto:|javascript:|tel:)")


def classificar(texto, categoria):
    t = norm(texto)
    for tipo in ORDEM:
        if tipo == "evento" and categoria not in ("faculdade", "local"):
            continue
        if tipo == "academico" and categoria == "local":
            continue
        if RX[tipo].search(t):
            return tipo
    return None


# ----------------------------------------------------------------- datas
_M = r"[a-zA-Zçã]{3,9}"
RE_RANGE_TXT = re.compile(
    rf"(?P<d1>\d{{1,2}})\s*º?(?:\s+de\s+(?P<m1>{_M}))?(?:\s+de\s+(?P<y1>\d{{4}}))?"
    rf"\s*(?:a|à|até|ate|e|-|–|—)\s*(?P<d2>\d{{1,2}})\s*º?\s+de\s+(?P<m2>{_M})(?:\s+de\s+(?P<y2>\d{{4}}))?", re.I)
RE_RANGE_NUM = re.compile(
    r"(?P<d1>\d{1,2})/(?P<m1>\d{1,2})(?:/(?P<y1>\d{2,4}))?\s*(?:a|à|até|ate|-|–|—)\s*"
    r"(?P<d2>\d{1,2})/(?P<m2>\d{1,2})(?:/(?P<y2>\d{2,4}))?")
RE_SINGLE_TXT = re.compile(rf"(?P<d>\d{{1,2}})\s*º?\s+de\s+(?P<m>{_M})(?:\s+de\s+(?P<y>\d{{4}}))?", re.I)
RE_SINGLE_NUM = re.compile(r"(?<![\d/])(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{2,4})(?![\d/])")
RE_YEAR = re.compile(r"\b(20[2-3]\d)\b")


def _mes(t):
    return MESES.get(norm(t)) if t else None


def _ano(y, fb):
    if not y:
        return fb
    y = int(y)
    return y + 2000 if y < 100 else y


def _mk(y, m, d):
    try:
        return dt.date(y, m, d)
    except (ValueError, TypeError):
        return None


def extract_dates(text, ref_year):
    anos = [int(a) for a in RE_YEAR.findall(text)]
    ano_ctx = anos[0] if anos else ref_year
    achados, usados = [], []
    livre = lambda sp: all(sp[1] <= a or sp[0] >= b for a, b in usados)

    def add(sp, ini, fim):
        if ini and fim:
            if fim < ini:
                fim = _mk(fim.year + 1, fim.month, fim.day) or fim
            achados.append((ini, fim))
            usados.append(sp)

    for m in RE_RANGE_NUM.finditer(text):
        y2 = _ano(m["y2"], None)
        y1 = _ano(m["y1"], y2 or ano_ctx)
        if livre(m.span()):
            add(m.span(), _mk(y1, int(m["m1"]), int(m["d1"])), _mk(y2 or y1, int(m["m2"]), int(m["d2"])))
    for m in RE_RANGE_TXT.finditer(text):
        m2 = _mes(m["m2"])
        if not m2 or not livre(m.span()):
            continue
        m1 = _mes(m["m1"]) if m["m1"] else m2
        if m["m1"] and not m1:
            continue
        y2 = _ano(m["y2"], ano_ctx)
        y1 = _ano(m["y1"], y2)
        add(m.span(), _mk(y1, m1, int(m["d1"])), _mk(y2, m2, int(m["d2"])))
    for m in RE_SINGLE_TXT.finditer(text):
        mm = _mes(m["m"])
        if mm and livre(m.span()):
            d = _mk(_ano(m["y"], ano_ctx), mm, int(m["d"]))
            add(m.span(), d, d)
    for m in RE_SINGLE_NUM.finditer(text):
        if livre(m.span()):
            d = _mk(_ano(m["y"], ano_ctx), int(m["m"]), int(m["d"]))
            add(m.span(), d, d)
    return achados


# ----------------------------------------------------------------- HTTP
_robots = {}


def pode_acessar(url):
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(root + "/robots.txt", headers={"User-Agent": UA}, timeout=10)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[root] = rp
    return _robots[root].can_fetch(UA, url)


def baixar(url, verify=True, tentativas=3):
    ultimo = None
    for i in range(tentativas):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
                             timeout=25, verify=verify)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa
            ultimo = e
            time.sleep(1.5 * (i + 1))
    raise ultimo


def host(u):
    return urlparse(u).netloc.lower().removeprefix("www.")


# ----------------------------------------------------------------- extração
def blocos_html(html):
    soup = BeautifulSoup(html, "lxml")
    links_soup = BeautifulSoup(html, "lxml")  # cópia intacta para os links
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        t.decompose()
    vistos, saida = set(), []
    for el in soup.find_all(["li", "p", "tr", "h1", "h2", "h3", "h4", "dd", "dt", "time", "article", "span", "div"]):
        if el.name in ("span", "div") and (el.find(True) or len(el.get_text(strip=True)) < 15):
            continue  # só folhas de texto
        if el.name in ("li", "p", "article") and el.find(["li", "p", "tr"]):
            continue
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if 12 <= len(txt) <= 700 and txt not in vistos:
            vistos.add(txt)
            saida.append(txt)
    return saida, links_soup


def blocos_pdf(conteudo):
    """Cada linha vira um bloco; se a linha é só um rótulo (sem data) e a seguinte tem data, junta as duas."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(conteudo))
    texto = "\n".join((p.extract_text() or "") for p in reader.pages[:40])
    linhas = [re.sub(r"\s+", " ", l).strip() for l in texto.splitlines() if l.strip()]
    tem_data = lambda l: bool(extract_dates(l, 2026))
    out = []
    for i, l in enumerate(linhas):
        prox = linhas[i + 1] if i + 1 < len(linhas) else ""
        if tem_data(l):
            out.append(l)
        elif prox and tem_data(prox) and len(l) < 140:
            out.append(f"{l} {prox}")
        elif len(l) > 8:
            out.append(l)
    return out


def itens_rss(xml):
    soup = BeautifulSoup(xml, "xml")
    out = []
    for it in soup.find_all(["item", "entry"]):
        titulo = it.find("title").get_text(" ", strip=True) if it.find("title") else ""
        desc = it.find(["description", "summary", "content"])
        corpo = BeautifulSoup(desc.get_text(), "lxml").get_text(" ", strip=True) if desc else ""
        link = it.find("link")
        href = (link.get("href") or link.get_text(strip=True)) if link else ""
        pub = it.find(["pubDate", "published", "updated"])
        out.append({"texto": f"{titulo}. {corpo}"[:700], "titulo": titulo, "url": href,
                    "pub": pub.get_text(strip=True) if pub else ""})
    return out


def links_relevantes(soup, base_url):
    docs, vistos = [], set()
    for a in soup.find_all("a", href=True):
        h = urljoin(base_url, a["href"]).split("#")[0]
        if not h.startswith("http") or SOCIAL.search(h) or h in vistos or h == base_url:
            continue
        txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if DOC_RX.search(norm(txt + " " + unquote(h))):
            vistos.add(h)
            pdf = ".pdf" in h.lower()
            docs.append({"titulo": (txt or unquote(h.rsplit("/", 1)[-1]))[:200], "url": h,
                         "tipo": "edital" if pdf or "edital" in norm(txt) else "link", "pub": ""})
    return docs[:300]


def eventos_de_blocos(blocos, fonte, url, hoje):
    filtro = re.compile(re.escape(norm(fonte["filtro"]))) if fonte.get("filtro") else None
    eventos = []
    for b in blocos:
        texto, link = (b["texto"], b["url"]) if isinstance(b, dict) else (b, url)
        if filtro and not filtro.search(norm(texto)):
            continue
        tipo = classificar(texto, fonte["categoria"])
        if not tipo:
            continue
        for ini, fim in extract_dates(texto, hoje.year):
            if abs((ini - hoje).days) > 800:
                continue
            eventos.append({"escopo": fonte["escopo"], "instituicao": fonte["nome"], "tipo": tipo,
                            "titulo": texto[:220], "inicio": ini.isoformat(), "fim": fim.isoformat(),
                            "url": link or url, "verificado": 0})
    return eventos


def processar_fonte(fonte, hoje, log=print):
    url, verify = fonte["url"], fonte.get("verify_ssl", True)
    if not fonte.get("ignorar_robots") and not pode_acessar(url):
        raise RuntimeError("bloqueado pelo robots.txt")
    r = baixar(url, verify)
    ctype = r.headers.get("content-type", "").lower()
    eventos, docs = [], []

    if fonte.get("tipo") == "rss" or "xml" in ctype:
        filtro = re.compile(re.escape(norm(fonte["filtro"]))) if fonte.get("filtro") else None
        itens = itens_rss(r.text)
        eventos += eventos_de_blocos(itens, fonte, url, hoje)
        for it in itens:
            t = norm(it["texto"])
            if (not filtro or filtro.search(t)) and (DOC_RX.search(t) or classificar(it["texto"], fonte["categoria"])):
                docs.append({"titulo": it["titulo"][:200], "url": it["url"], "tipo": "noticia", "pub": it["pub"]})
    elif url.lower().endswith(".pdf") or "pdf" in ctype:
        eventos += eventos_de_blocos(blocos_pdf(r.content), fonte, url, hoje)
        docs.append({"titulo": unquote(url.rsplit("/", 1)[-1]), "url": url, "tipo": "edital", "pub": ""})
    else:
        blocos, soup = blocos_html(r.content)
        eventos += eventos_de_blocos(blocos, fonte, url, hoje)
        docs = links_relevantes(soup, url)
        seguir = fonte.get("seguir", fonte["categoria"] in ("educacao", "faculdade"))
        pat = re.compile(fonte["follow_pattern"], re.I) if fonte.get("follow_pattern") else None
        extras = set(fonte.get("dominios_extras", []))
        cand = []
        for d in docs:
            ok_host = host(d["url"]) == host(url) or host(d["url"]) in extras
            if (seguir and ok_host) or (pat and pat.search(d["url"])):
                cand.append(d)
        cand.sort(key=lambda d: (d["tipo"] != "edital", ".pdf" not in d["url"].lower()))
        for d in cand[: fonte.get("max_follow", 12)]:
            time.sleep(DELAY)
            try:
                if not pode_acessar(d["url"]):
                    continue
                rr = baixar(d["url"], verify, tentativas=2)
                if len(rr.content) > MAX_PDF_MB * 1e6:
                    continue
                if ".pdf" in d["url"].lower() or "pdf" in rr.headers.get("content-type", "").lower():
                    bl = blocos_pdf(rr.content)
                else:
                    bl, _ = blocos_html(rr.content)
                eventos += eventos_de_blocos(bl, fonte, d["url"], hoje)
            except Exception as e:  # noqa
                log(f"    ! não consegui seguir {d['url'][:80]}: {type(e).__name__}")
    for d in docs:
        d["instituicao"] = fonte["nome"]
    return eventos, docs


# ----------------------------------------------------------------- fontes
def gnews(nome, escopo, categoria, consulta, filtro=None):
    q = quote_plus(consulta + " when:90d")
    return {"nome": nome, "escopo": escopo, "categoria": categoria, "tipo": "rss", "filtro": filtro,
            "ignorar_robots": True,  # feed RSS feito para consumo automatizado
            "url": f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"}


def expandir(cfg):
    fontes = [f for f in cfg["fontes"] if f.get("ativo", True)]
    for mod in cfg.get("gnews_por_municipio", []):
        for m in cfg.get("municipios", []):
            fontes.append(gnews("Notícias (Google News)", mod["escopo"], mod["categoria"],
                                mod["consulta"].replace("{m}", m), filtro=m))
    for g in cfg.get("gnews_gerais", []):
        fontes.append(gnews("Notícias (Google News)", g["escopo"], g["categoria"], g["consulta"], g.get("filtro")))
    return fontes


# ----------------------------------------------------------------- banco
def conectar():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS eventos(
        id TEXT PRIMARY KEY, escopo TEXT, instituicao TEXT, tipo TEXT, titulo TEXT, inicio TEXT, fim TEXT,
        url TEXT, verificado INTEGER DEFAULT 0, obs TEXT, primeira_vez TEXT, ultima_vez TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS documentos(
        id TEXT PRIMARY KEY, instituicao TEXT, titulo TEXT, tipo TEXT, url TEXT, pub TEXT,
        primeira_vez TEXT, ultima_vez TEXT)""")
    return con


def chave(e):
    extra = norm(e["titulo"])[:50] if e["instituicao"].startswith("Notícias") else ""
    return hashlib.sha1(f"{norm(e['instituicao'])}|{e['tipo']}|{e['inicio']}|{e['fim']}|{extra}".encode()).hexdigest()[:16]


def salvar(con, eventos, agora):
    novos = []
    for e in eventos:
        k = chave(e)
        if con.execute("SELECT 1 FROM eventos WHERE id=?", (k,)).fetchone() is None:
            con.execute("INSERT INTO eventos VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (k, e["escopo"], e["instituicao"], e["tipo"], e["titulo"], e["inicio"], e["fim"],
                         e["url"], e.get("verificado", 0), e.get("obs", ""), agora, agora))
            novos.append(e)
        else:
            con.execute("UPDATE eventos SET ultima_vez=? WHERE id=?", (agora, k))
            if e.get("verificado"):
                con.execute("UPDATE eventos SET verificado=1, obs=?, titulo=? WHERE id=?", (e.get("obs", ""), e["titulo"], k))
    con.commit()
    return novos


def salvar_docs(con, docs, agora):
    novos = []
    for d in docs:
        if not d.get("url"):
            continue
        k = hashlib.sha1(d["url"].encode()).hexdigest()[:16]
        if con.execute("SELECT 1 FROM documentos WHERE id=?", (k,)).fetchone() is None:
            con.execute("INSERT INTO documentos VALUES(?,?,?,?,?,?,?,?)",
                        (k, d["instituicao"], d["titulo"], d["tipo"], d["url"], d.get("pub", ""), agora, agora))
            novos.append(d)
        else:
            con.execute("UPDATE documentos SET ultima_vez=? WHERE id=?", (agora, k))
    con.commit()
    return novos


def carregar_base(con, agora):
    f = BASE / "eventos_base.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8") as fh:
        eventos = []
        for r in csv.DictReader(fh):
            r["fim"] = r.get("fim") or r["inicio"]
            r["verificado"] = int(r.get("verificado") or 1)
            eventos.append(r)
    return salvar(con, eventos, agora)


# ----------------------------------------------------------------- exportação
def prazos_proximos(con, hoje, dias):
    lim = (hoje + dt.timedelta(days=dias)).isoformat()
    q = """SELECT instituicao,tipo,titulo,inicio,fim,url FROM eventos
           WHERE tipo IN ('inscricao','isencao','matricula') AND fim>=? AND fim<=? AND verificado=1
           ORDER BY fim"""
    return con.execute(q, (hoje.isoformat(), lim)).fetchall()


def exportar(con, hoje, todos=False, dias_alerta=7):
    SAIDA.mkdir(exist_ok=True)
    q = "SELECT escopo,instituicao,tipo,titulo,inicio,fim,url,verificado,obs FROM eventos"
    if not todos:
        q += f" WHERE fim >= '{hoje.isoformat()}'"
    q += " ORDER BY inicio, instituicao"
    cols = ["escopo", "instituicao", "tipo", "titulo", "inicio", "fim", "url", "verificado", "obs"]
    rows = [dict(zip(cols, r)) for r in con.execute(q)]
    dcols = ["instituicao", "tipo", "titulo", "url", "pub", "primeira_vez"]
    docs = [dict(zip(dcols, r)) for r in con.execute(
        "SELECT instituicao,tipo,titulo,url,pub,primeira_vez FROM documentos ORDER BY primeira_vez DESC, tipo LIMIT 1500")]
    (SAIDA / "eventos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (SAIDA / "documentos.json").write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    for nome, dados, campos in (("eventos.csv", rows, cols), ("documentos.csv", docs, dcols)):
        with (SAIDA / nome).open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            w.writerows(dados)
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Agenda Vale do Ribeira//PT",
           "X-WR-CALNAME:Agenda Vale do Ribeira", "X-WR-TIMEZONE:America/Sao_Paulo"]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")
    for r in rows:
        ini = dt.date.fromisoformat(r["inicio"])
        fim = dt.date.fromisoformat(r["fim"]) + dt.timedelta(days=1)
        uid = hashlib.sha1(f"{r['instituicao']}{r['tipo']}{r['inicio']}{r['fim']}{r['titulo'][:30]}".encode()).hexdigest()[:20]
        resumo = f"[{r['instituicao']}] {r['tipo'].capitalize()}: {r['titulo'][:70]}"
        desc = r["titulo"] + (" | " + r["obs"] if r["obs"] else "") + " | " + (r["url"] or "")
        ics += ["BEGIN:VEVENT", f"UID:{uid}@agenda-vale", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{ini:%Y%m%d}",
                f"DTEND;VALUE=DATE:{fim:%Y%m%d}", f"SUMMARY:{esc(resumo)}", f"DESCRIPTION:{esc(desc)}", "END:VEVENT"]
    ics.append("END:VCALENDAR")
    (SAIDA / "eventos.ics").write_text("\r\n".join(ics), encoding="utf-8")
    pp = prazos_proximos(con, hoje, dias_alerta)
    linhas = [f"⏰ Prazos que fecham nos próximos {dias_alerta} dias ({hoje:%d/%m/%Y}):"] + [
        f"• até {dt.date.fromisoformat(f):%d/%m} [{i}] {t}: {ti[:80]}" for i, t, ti, _, f, _ in pp]
    (SAIDA / "prazos_proximos.txt").write_text("\n".join(linhas) if pp else "Nenhum prazo verificado fechando em breve.",
                                               encoding="utf-8")
    painel(rows, docs, hoje)
    return rows, docs, pp


def painel(rows, docs, hoje):
    tpl = (BASE / "painel_template.html").read_text(encoding="utf-8")
    dados = json.dumps({"hoje": hoje.isoformat(), "eventos": rows, "docs": docs}, ensure_ascii=False).replace("</", "<\\/")
    (SAIDA / "index.html").write_text(tpl.replace("%%DADOS%%", dados), encoding="utf-8")


def notificar(novos, pp, docs_novos):
    SAIDA.mkdir(exist_ok=True)
    partes = []
    if pp:
        partes.append("⏰ Prazos fechando em breve:\n" + "\n".join(
            f"• até {dt.date.fromisoformat(f):%d/%m} [{i}] {t}: {ti[:70]}" for i, t, ti, _, f, _ in pp))
    if novos:
        partes.append(f"🆕 {len(novos)} evento(s) novo(s):\n" + "\n".join(
            f"• {e['inicio']}" + (f" → {e['fim']}" if e['fim'] != e['inicio'] else "") +
            f" [{e['instituicao']}] {e['tipo']}: {e['titulo'][:80]}" for e in novos[:20]))
    eds = [d for d in docs_novos if d["tipo"] == "edital"]
    if eds:
        partes.append(f"📄 {len(eds)} edital(is)/PDF novo(s):\n" + "\n".join(
            f"• [{d['instituicao']}] {d['titulo'][:70]} {d['url']}" for d in eds[:10]))
    texto = "\n\n".join(partes)
    (SAIDA / "novos.txt").write_text(texto or "Sem novidades.", encoding="utf-8")
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if texto and tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": True}, timeout=15)
        except Exception as e:  # noqa
            print("Telegram falhou:", e)


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--sem-noticias", action="store_true")
    ap.add_argument("--alerta-dias", type=int, default=7)
    ap.add_argument("--fontes", default=str(BASE / "fontes.json"))
    a = ap.parse_args()

    hoje = dt.date.today()
    agora = dt.datetime.now().isoformat(timespec="seconds")
    fontes = expandir(json.loads(Path(a.fontes).read_text(encoding="utf-8")))
    if a.only:
        fontes = [f for f in fontes if a.only.lower() in f["nome"].lower()]
    if a.sem_noticias:
        fontes = [f for f in fontes if not f["nome"].startswith("Notícias")]

    con = conectar()
    novos = [] if a.check else carregar_base(con, agora)
    docs_novos, falhas = [], 0
    for f in fontes:
        rotulo = f["nome"] if not f["nome"].startswith("Notícias") else f"Notícias: {f.get('filtro') or f['url'][45:80]}"
        try:
            ev, docs = processar_fonte(f, hoje)
            print(f"[OK ] {rotulo[:44]:<44} {len(ev):>3} datas {len(docs):>3} links")
            if not a.check:
                novos += salvar(con, ev, agora)
                docs_novos += salvar_docs(con, docs, agora)
        except Exception as e:  # noqa
            falhas += 1
            print(f"[ERR] {rotulo[:44]:<44} {type(e).__name__}: {str(e)[:80]}")
        time.sleep(DELAY)
    if a.check:
        return
    rows, docs, pp = exportar(con, hoje, a.all, a.alerta_dias)
    notificar([e for e in novos if e["fim"] >= hoje.isoformat()], pp, docs_novos)
    print(f"\n{len(rows)} eventos | {len(docs)} editais/links | {len(novos)} eventos novos | "
          f"{len(docs_novos)} links novos | {falhas} fontes com erro -> {SAIDA}/")


if __name__ == "__main__":
    main()
