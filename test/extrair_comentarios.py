"""
Extrai comentários dos posts já baixados de @camisart_belem.
Lê os shortcodes do _resumo.json e busca os comentários de cada post.
Útil para identificar dúvidas, sugestões e elogios dos clientes.
"""
import json
import os
import time
import instaloader

PERFIL = "camisart_belem"
PASTA_POSTS = os.path.join("dados_instagram", PERFIL)
PASTA_SAIDA = os.path.join("dados_instagram", PERFIL, "comentarios")
PAUSA_SEGUNDOS = 4   # pausa entre posts para não ser bloqueado

os.makedirs(PASTA_SAIDA, exist_ok=True)

# ── Autenticação ──────────────────────────────────────────────────────────────
loader = instaloader.Instaloader(download_pictures=False)
INSTAGRAM_USER = input("Seu nome de usuário Instagram (sem @): ").strip()

try:
    loader.load_session_from_file(INSTAGRAM_USER)
    print(f"Sessão carregada para @{INSTAGRAM_USER}.\n")
except FileNotFoundError:
    print(f"Sessão não encontrada. Execute: instaloader --login {INSTAGRAM_USER}")
    exit(1)

# ── Carrega posts já baixados ─────────────────────────────────────────────────
resumo_path = os.path.join(PASTA_POSTS, "_resumo.json")
with open(resumo_path, encoding="utf-8") as f:
    resumo = json.load(f)

posts = resumo["posts"]
print(f"Posts encontrados: {len(posts)}")

# Pula posts cujos comentários já foram extraídos
ja_extraidos = {
    f.replace("_comentarios.json", "")
    for f in os.listdir(PASTA_SAIDA)
    if f.endswith("_comentarios.json")
}
posts_pendentes = [p for p in posts if p["shortcode"] not in ja_extraidos]
print(f"Já extraídos:      {len(ja_extraidos)}")
print(f"Pendentes:         {len(posts_pendentes)}\n")

# ── Extração dos comentários ──────────────────────────────────────────────────
todos_comentarios = []
erros = []

for i, post_info in enumerate(posts_pendentes, 1):
    shortcode = post_info["shortcode"]
    print(f"[{i:02d}/{len(posts_pendentes)}] {post_info['data']} | {shortcode}", end=" ... ")

    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        comentarios = []

        for comentario in post.get_comments():
            comentarios.append({
                "autor":    comentario.owner.username,
                "texto":    comentario.text,
                "data":     comentario.created_at_utc.strftime("%Y-%m-%d"),
                "curtidas": comentario.likes_count,
            })

        # Salva JSON individual do post
        saida = {
            "shortcode":         shortcode,
            "url":               post_info["url"],
            "data_post":         post_info["data"],
            "legenda":           post_info["legenda"],
            "total_comentarios": len(comentarios),
            "comentarios":       comentarios,
        }
        caminho = os.path.join(PASTA_SAIDA, f"{shortcode}_comentarios.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(saida, f, ensure_ascii=False, indent=2)

        todos_comentarios.append(saida)
        print(f"{len(comentarios)} comentários")
        time.sleep(PAUSA_SEGUNDOS)

    except Exception as e:
        print(f"ERRO: {e}")
        erros.append({"shortcode": shortcode, "erro": str(e)})
        continue

# ── Consolidação ──────────────────────────────────────────────────────────────
# Reconstrói o resumo com TODOS os arquivos da pasta (antigos + novos)
todos_arquivos = []
for nome in sorted(os.listdir(PASTA_SAIDA)):
    if nome.endswith("_comentarios.json"):
        with open(os.path.join(PASTA_SAIDA, nome), encoding="utf-8") as f:
            todos_arquivos.append(json.load(f))

# Flatten: lista única de todos os comentários com referência ao post
comentarios_flat = []
for post_data in todos_arquivos:
    for c in post_data["comentarios"]:
        comentarios_flat.append({
            "post_shortcode": post_data["shortcode"],
            "post_url":       post_data["url"],
            "post_data":      post_data["data_post"],
            "autor":          c["autor"],
            "texto":          c["texto"],
            "data":           c["data"],
            "curtidas":       c["curtidas"],
        })

resumo_comentarios = {
    "perfil":                   PERFIL,
    "total_posts_com_comentarios": len(todos_arquivos),
    "total_comentarios":        len(comentarios_flat),
    "comentarios":              comentarios_flat,
}

resumo_path = os.path.join(PASTA_POSTS, "_resumo_comentarios.json")
with open(resumo_path, "w", encoding="utf-8") as f:
    json.dump(resumo_comentarios, f, ensure_ascii=False, indent=2)

print(f"\n{'='*50}")
print(f"Comentários novos extraídos: {sum(len(p['comentarios']) for p in todos_comentarios)}")
print(f"Total acumulado:             {len(comentarios_flat)}")
print(f"Erros:                       {len(erros)}")
print(f"Resumo salvo em:             {resumo_path}")
