"""Serveur local : sert les pages ET génère les résumés à la demande (DeepSeek), avec cache.
Usage (depuis lecteur/) :  python ../serveur.py      puis ouvre http://localhost:8000/fils.html"""
import collections, hashlib, json, math, os, re, threading, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

def cle_env():
    cle = None
    for p in (".env", "../.env", "../../.env"):
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                l = l.strip()
                if "=" in l and not l.startswith("#"):
                    k, v = l.split("=", 1)
                    if "DEEPSEEK" in k.upper() and v.strip().strip("'\""): cle = v.strip().strip("'\""); break
        if cle: break
    cle = cle or os.environ.get("DEEPSEEK_API_KEY")
    if not cle or "xxxx" in cle:
        exit("Clé DeepSeek introuvable : copie .env.example en .env (à la racine du repo) et colle ta clé dedans.")
    return cle

KEY = cle_env()
lire = lambda p, o, c: json.loads((lambda s: s[s.index(o): s.rindex(c) + 1])(open(p, encoding="utf-8").read()))
FILS, IDX = lire("data/fils.js", "[", "]"), lire("data/index.js", "[", "]")
CF = "data/cache_resumes.json"
cache = json.load(open(CF, encoding="utf-8")) if os.path.exists(CF) else {}
lock = threading.Lock()
ONLY_FILS = True     # recherche d'autres papiers : seulement parmi ceux présents dans les fils (cliquables dans la page). False = tout l'index.
INFIL = {p["i"] for f in FILS for p in f["pts"]}

# ---------- profil du lecteur (modifiable dans lecteur/profil.json) ----------
CFG = {"profil": "Le lecteur est doctorant en NLP (traitement automatique des langues) : il connaît très bien les LLM, "
        "les architectures Transformer, le pré-entraînement et le fine-tuning, les représentations, la sémantique, "
        "les protocoles d'évaluation et les benchmarks usuels du domaine. Ne lui explique jamais les notions de base. "
        "Il est moins familier des mathématiques de l'optimisation, de la vision et de la robotique.", "focus": ""}
PROFIL = VERSION = ""
def appliquer_profil():
    global PROFIL, VERSION
    PROFIL = (CFG["profil"].strip()
              + (" Priorité de fond pour ce lecteur : " + CFG["focus"].strip() if CFG.get("focus", "").strip() else "")
              + " Ces consignes portent sur le fond ; le format de sortie demandé plus bas reste inchangé.")
    VERSION = "v3-" + hashlib.md5(PROFIL.encode()).hexdigest()[:6]   # le cache s'invalide tout seul si le profil change
if os.path.exists("profil.json"): CFG.update(json.load(open("profil.json", encoding="utf-8")))
appliquer_profil()
NOM = {"lim": "une limite que plusieurs papers avouent", "hyp": "une hypothèse que plusieurs papers posent",
       "opp": "un point que plusieurs papers critiquent"}

# ---------- fils ----------
def prompt_fil(f, niv):
    ex = f["pts"][:4] + [p for p in f["pts"][-3:] if p not in f["pts"][:4]]
    txt = "\n".join(f"- ({IDX[p['i']][1]}) {p['t']}" for p in ex)
    base = f"Voici un fil de réflexion (idée récurrente) repéré dans des papers NeurIPS 2026 : {NOM[f['type']]}. Extraits, du plus proche au plus éloigné de l'énoncé de départ :\n{txt}\n\n"
    if niv == "simple":
        return base + "Explique en 2 ou 3 phrases très simples en français, sans jargon, comprises par n'importe qui : l'idée suivie, comment elle change du début à la fin, ce qui la distingue. Réponds uniquement par ces phrases."
    return base + PROFIL + (" Rédige en français 4 à 6 phrases denses pour ce lecteur : (1) la thèse sous-jacente du fil, formulée précisément ; "
        "(2) comment elle se déplace ou se radicalise entre les extraits (changement de cadre, de tâche, de métrique, d'hypothèse) ; "
        "(3) ce qu'elle implique pour la recherche en NLP : quel travail existant elle conforte, remet en cause ou rend évaluable, et quelle expérience ou quel protocole on pourrait en tirer "
        "(si le fil est éloigné du langage, dis-le en une phrase et indique si un transfert est plausible) ; "
        "(4) une question ouverte ou un point critique (confound, biais d'évaluation, généralisation douteuse). "
        "Vocabulaire technique et termes anglais usuels permis, aucune vulgarisation. N'invente rien qui ne soit pas dans les extraits ; signale ce qui est de l'extrapolation. Réponds uniquement par le résumé.")

# ---------- accès aux papiers ----------
def charger(i):
    d, p = IDX[i], {}
    try: p = lire(f"data/p/{d[0]}.js", "{", "}")
    except Exception: pass
    return d, p

SEC = {"abs": "ABSTRACT", "intro": "INTRODUCTION", "limitations": "LIMITES", "conclusion": "CONCLUSION"}
norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()

def sections(i):
    d, p = charger(i)
    return d, {"abs": (p.get("abs") or str(d[7]))[:1800], "intro": (p.get("intro") or "")[:2000],
               "limitations": (p.get("limitations") or "")[:1500], "conclusion": (p.get("conclusion") or "")[:1000]}

# ---------- résumé structuré d'un paper ----------
SCHEMA = """{
 "probleme": {"t": "...", "clair": "..."},
 "idee": {"t": "...", "clair": "..."},
 "resultat": {"t": "...", "clair": "..."},
 "limites": [{"t": "...", "clair": "...", "cite": "...", "q": "..."}],
 "apports": [{"t": "...", "clair": "...", "cite": "..."}]
}"""

def prompt_papier_expert(titre, src):
    corps = f"[TITRE] {titre}\n" + "".join(f"[{SEC[k]}] {v}\n" for k, v in src.items() if v)
    return ("Voici des extraits d'un paper NeurIPS 2026.\n\n" + corps + "\n" + PROFIL + "\n\n"
        "Réponds UNIQUEMENT par un objet JSON, en français, de cette forme exacte :\n" + SCHEMA + "\n\n"
        "Règles :\n"
        "- \"t\" : une seule phrase courte (20 mots max), vocabulaire technique permis.\n"
        "- \"clair\" : une seule phrase (25 mots max) en mots simples, sans jargon, comprise par un non-spécialiste.\n"
        "- probleme / idee / resultat : la réflexion du paper (quelle question, quelle idée centrale, qu'est-ce qui est montré). Ne recopie pas l'abstract, va à l'essentiel.\n"
        "- limites : UNIQUEMENT les limites que le paper reconnaît lui-même (3 max). S'il n'en reconnaît aucune dans le texte, renvoie [].\n"
        "- apports : UNIQUEMENT les contributions, implications ou pistes futures que le paper affirme lui-même ET qui concernent le langage, les modèles de langue ou la recherche en NLP (3 max). "
        "Si le paper n'affirme rien de tel, renvoie []. N'extrapole jamais, ne propose pas tes propres apports.\n"
        "- \"cite\" : extrait EXACT, mot pour mot, copié du texte ci-dessus (4 à 15 mots, sans \"...\"), qui prouve la limite ou l'apport.\n"
        "- \"q\" (limites seulement) : 3 à 6 mots-clés ANGLAIS décrivant ce qu'il faudrait résoudre pour lever cette limite.\n"
        "- N'invente rien.")

def bloc(x):
    if isinstance(x, dict) and str(x.get("t", "")).strip():
        return {"t": str(x["t"]).strip(), "clair": str(x.get("clair", "")).strip()}

def items(lst, src, extra=()):
    out = []
    for x in (lst if isinstance(lst, list) else [])[:3]:
        if not (isinstance(x, dict) and str(x.get("t", "")).strip()): continue
        o = {"t": str(x["t"]).strip(), "clair": str(x.get("clair", "")).strip(), "cite": str(x.get("cite", "")).strip()}
        for e in extra: o[e] = str(x.get(e, "")).strip()
        c, o["src"] = norm(o["cite"]), None            # vérification : l'extrait est-il vraiment dans le texte ?
        if len(c.split()) >= 3:
            for k, v in src.items():
                if c in norm(v): o["src"] = k; break
        out.append(o)
    return out

def resume_papier(i):
    d, src = sections(i)
    r = deepseek_json(prompt_papier_expert(d[1], src))
    return {"probleme": bloc(r.get("probleme")), "idee": bloc(r.get("idee")), "resultat": bloc(r.get("resultat")),
            "limites": items(r.get("limites"), src, ("q",)), "apports": items(r.get("apports"), src)}

# ---------- autres papiers qui traitent les limites ----------
STOP = set("""the and for with that this are was were from have has had not can will our their its into over under than then them these
those which while where when what how also such more most other using use used based via per each both between within without across through
only very may might could would should paper papers model models method methods approach propose proposed show shows results result new""".split())
tok = lambda s: [w for w in re.findall(r"[a-z][a-z\-]{2,}", (s or "").lower()) if w not in STOP]
DOCS = [tok(f"{d[1]} {d[1]} {d[7]}") for d in IDX]
TF = [collections.Counter(t) for t in DOCS]
DF = collections.Counter(w for t in TF for w in t)
N, AVG = len(DOCS), sum(len(t) for t in DOCS) / max(len(DOCS), 1)

def bm25(q, n, k1=1.5, b=.75):
    s, L = 0.0, len(DOCS[n])
    for w in set(q):
        f = TF[n].get(w, 0)
        if f: s += math.log(1 + (N - DF[w] + .5) / (DF[w] + .5)) * f * (k1 + 1) / (f + k1 * (1 - b + b * L / AVG))
    return s

def voisins(texte, exclu, k=4):
    q = tok(texte)
    pool = INFIL if ONLY_FILS else range(N)
    sc = sorted(((bm25(q, n), n) for n in pool if n != exclu), reverse=True)[:k]
    return [n for s, n in sc if s > 0]

def chercher_liens(i):
    r = resume({"kind": "pap", "id": i, "niveau": "expert"})
    lim = [(n, l) for n, l in enumerate(r["limites"], 1) if l.get("src")]   # seulement les limites vérifiées dans le texte
    if not lim: return []
    cands = {}
    for n, l in lim:
        for c in voisins(l["cite"] + " " + l.get("q", ""), i): cands.setdefault(c, n)
    if not cands: return []
    nums = {n for n, _ in lim}
    prompt = (f"Le paper « {IDX[i][1]} » reconnaît lui-même ces limites :\n" +
              "\n".join(f"{n}. {l['t']} (extrait : « {l['cite']} »)" for n, l in lim) +
              "\n\nVoici des papiers candidats du même corpus (identifiant entre crochets, titre, début d'abstract) :\n" +
              "\n".join(f"[{c}] {IDX[c][1]} — {str(IDX[c][7])[:400]}" for c in cands) +
              "\n\nRetiens UNIQUEMENT les candidats dont le titre ou l'abstract montre clairement qu'ils s'attaquent à l'une de ces limites (3 au plus au total). "
              "Une simple proximité de sujet ne suffit pas. N'invente rien. Si aucun ne convient, renvoie une liste vide.\n"
              "Réponds UNIQUEMENT en JSON : {\"liens\": [{\"id\": <identifiant du candidat>, \"limite\": <numéro de la limite>, "
              "\"pourquoi\": \"une phrase technique en français (25 mots max) appuyée sur l'abstract du candidat\", "
              "\"clair\": \"la même idée en mots simples, sans jargon (25 mots max)\"}]}")
    out = []
    for l in (deepseek_json(prompt, 700).get("liens") or [])[:3]:
        try: cid, n = int(l["id"]), int(l["limite"])
        except Exception: continue
        if cid in cands and n in nums:
            out.append({"id": cid, "limite": n, "pourquoi": str(l.get("pourquoi", "")).strip(), "clair": str(l.get("clair", "")).strip()})
    return out

# ---------- contexte : pourquoi ce paper est dans ce fil ----------
def resume_ctx(b):
    k, j, i = int(b["fil"]), int(b["pos"]), int(b["id"])
    f = FILS[k]
    if f["question"][:60] != b.get("cle") or f["pts"][j]["i"] != i: raise ValueError("fils.js a changé : recharge la page")
    return deepseek(f"Un fil de réflexion (idée récurrente dans des papers NeurIPS 2026) part de l'énoncé : « {f['question'][:400]} ». "
        f"Le paper « {IDX[i][1]} » y est rattaché par cette phrase : « {f['pts'][j]['t']} ».\n"
        "Explique en UNE phrase simple (30 mots max), sans jargon, ce que dit cette phrase et en quoi elle rejoint l'idée du fil. "
        "N'invente rien. Réponds uniquement par cette phrase.", 150)

def prompt_papier_simple(i):
    d, src = sections(i)
    txt = f"Titre : {d[1]}\nAbstract : {src['abs']}\nIntroduction (extrait) : {src['intro'][:1500]}\n\n"
    return txt + "Explique en 2 ou 3 phrases très simples en français, sans jargon, comprises par n'importe qui. Réponds uniquement par ces phrases."

# ---------- DeepSeek ----------
def deepseek(prompt, max_tokens=700, js=False):
    body = {"model": "deepseek-chat", "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if js: body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", method="POST",
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, data=json.dumps(body).encode())
    return json.load(urllib.request.urlopen(req, timeout=90))["choices"][0]["message"]["content"].strip()

def deepseek_json(prompt, max_tokens=1200):
    t = deepseek(prompt, max_tokens, js=True)
    try: return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if not m: raise ValueError("Réponse DeepSeek illisible : réessaie.")
        return json.loads(m.group(0))

# ---------- routage + cache ----------
def resume(b):
    niv, kind = b.get("niveau", "expert"), b["kind"]
    i = int(b["id"])
    if kind == "fil":
        if FILS[i]["question"][:60] != b.get("cle"): raise ValueError("fils.js a changé : recharge la page")
        ck, mk = f"fil|{b['cle']}|{niv}|{VERSION}", lambda: deepseek(prompt_fil(FILS[i], niv))
    elif kind == "ctx":
        ck, mk = f"ctx|{b.get('cle')}|{b['pos']}|{i}|{VERSION}", lambda: resume_ctx(b)
    elif kind == "liens":
        ck, mk = f"lnk|{IDX[i][0]}|{VERSION}", lambda: {"liens": chercher_liens(i)}
    elif niv == "simple":
        ck, mk = f"pap|{IDX[i][0]}|simple|{VERSION}", lambda: deepseek(prompt_papier_simple(i))
    else:
        ck, mk = f"pap|{IDX[i][0]}|expert|{VERSION}", lambda: resume_papier(i)
    if ck in cache: return cache[ck]
    t = mk()
    with lock:
        cache[ck] = t
        json.dump(cache, open(CF, "w", encoding="utf-8"), ensure_ascii=False)
    return t

def repondre(h, out, code=200):
    d = json.dumps(out, ensure_ascii=False).encode()
    h.send_response(code); h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(d))); h.end_headers(); h.wfile.write(d)

class H(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin == "/api/profil": return repondre(self, CFG)
        # première utilisation : pas encore de profil.json -> on demande le profil d'abord
        if chemin in ("/", "/fils.html") and not os.path.exists("profil.json"):
            self.send_response(302); self.send_header("Location", "/profil.html"); self.end_headers(); return
        super().do_GET()
    def do_POST(self):
        try:
            b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/profil":
                p = str(b.get("profil", "")).strip()
                if not p: raise ValueError("Le profil ne peut pas être vide.")
                CFG["profil"], CFG["focus"] = p, str(b.get("focus", "")).strip()
                json.dump(CFG, open("profil.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                appliquer_profil()
                return repondre(self, {"ok": True})
            res = resume(b)
            out = {"data": res} if isinstance(res, dict) else {"texte": res}
        except Exception as e:
            out = {"error": str(e)}
        repondre(self, out)
    def log_message(self, *a): pass

print("Ouvre : http://localhost:8000/fils.html   (Ctrl+C pour arrêter)")
ThreadingHTTPServer(("", 8000), H).serve_forever()
