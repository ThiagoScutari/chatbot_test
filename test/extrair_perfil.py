"""
Extrai todos os posts de um perfil público do Instagram.
Salva legenda + URL das imagens em JSON por post.
Gera um arquivo resumo com todos os posts juntos.
"""
import json
import os
import time
import instaloader

PERFIL = "camisart_belem"
PASTA_SAIDA = os.path.join("dados_instagram", PERFIL)
MAX_POSTS = 50        # quantos posts NOVOS buscar por execução
PAUSA_SEGUNDOS = 3    # pausa entre requests para não ser bloqueado

os.makedirs(PASTA_SAIDA, exist_ok=True)

loader = instaloader.Instaloader(
    download_pictures=True,
    download_videos=False,
    download_video_thumbnails=False,
    download_comments=False,
    save_metadata=False,
    post_metadata_txt_pattern="",
    dirname_pattern=PASTA_SAIDA,
)

# Autenticação via arquivo de sessão do instaloader
#
# ANTES de rodar este script, gere o arquivo de sessão uma única vez:
#   instaloader --login SEU_USUARIO
# Isso cria o arquivo: C:\Users\<você>\AppData\Roaming\instaloader\session-SEU_USUARIO
#
INSTAGRAM_USER = input("Seu nome de usuário Instagram (sem @): ").strip()

try:
    loader.load_session_from_file(INSTAGRAM_USER)
    print(f"Sessão carregada para @{INSTAGRAM_USER}.\n")
except FileNotFoundError:
    print(f"\nArquivo de sessão não encontrado.")
    print(f"Execute primeiro no terminal:")
    print(f"  instaloader --login {INSTAGRAM_USER}")
    print(f"Depois rode este script novamente.\n")
    exit(1)

print(f"Extraindo posts de @{PERFIL} (máximo: {MAX_POSTS})\n")

profile = instaloader.Profile.from_username(loader.context, PERFIL)

print(f"Perfil encontrado: {profile.full_name}")
print(f"Seguidores: {profile.followers}")
print(f"Total de posts: {profile.mediacount}\n")

# Carrega shortcodes já baixados para não repetir
ja_baixados = {
    f.replace(".json", "")
    for f in os.listdir(PASTA_SAIDA)
    if f.endswith(".json") and not f.startswith("_")
}
print(f"Posts já baixados: {len(ja_baixados)}")
print(f"Buscando mais {MAX_POSTS} posts novos...\n")

todos_posts = []
erros = []
novos = 0

for post in profile.get_posts():
    if novos >= MAX_POSTS:
        print(f"\nLimite de {MAX_POSTS} posts novos atingido.")
        break

    # Pula posts já baixados (retomada automática)
    if post.shortcode in ja_baixados:
        continue

    novos += 1
    try:
        # Coleta as imagens (carrossel ou post simples)
        imagens = []
        if post.typename == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                imagens.append(node.display_url)
        else:
            imagens.append(post.url)

        dados = {
            "shortcode": post.shortcode,
            "url":       f"https://www.instagram.com/p/{post.shortcode}/",
            "data":      post.date_utc.strftime("%Y-%m-%d"),
            "curtidas":  post.likes,
            "legenda":   post.caption or "",
            "hashtags":  list(post.caption_hashtags),
            "imagens":   imagens,
        }

        # Salva JSON individual
        caminho = os.path.join(PASTA_SAIDA, f"{post.shortcode}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

        # Baixa a imagem do post
        loader.download_post(post, target=PASTA_SAIDA)

        todos_posts.append(dados)

        legenda_curta = (dados["legenda"][:60] + "...") if len(dados["legenda"]) > 60 else dados["legenda"]
        print(f"[{novos:02d}] {dados['data']} | {len(imagens)} img | {legenda_curta!r}")

        time.sleep(PAUSA_SEGUNDOS)   # respeita o rate limit do Instagram

    except Exception as e:
        print(f"[{novos:02d}] ERRO no post {post.shortcode}: {e}")
        erros.append({"shortcode": post.shortcode, "erro": str(e)})
        continue

# Reconstrói o resumo com TODOS os JSONs da pasta (antigos + novos)
resumo_path = os.path.join(PASTA_SAIDA, "_resumo.json")
todos_jsons = []
for nome in sorted(os.listdir(PASTA_SAIDA)):
    if nome.endswith(".json") and not nome.startswith("_"):
        with open(os.path.join(PASTA_SAIDA, nome), encoding="utf-8") as f:
            todos_jsons.append(json.load(f))

with open(resumo_path, "w", encoding="utf-8") as f:
    json.dump({
        "perfil":      PERFIL,
        "total_posts": len(todos_jsons),
        "erros":       len(erros),
        "posts":       todos_jsons,
    }, f, ensure_ascii=False, indent=2)

print(f"\n{'='*50}")
print(f"Novos posts extraídos: {len(todos_posts)}")
print(f"Total acumulado:       {len(todos_jsons)}")
print(f"Erros:                 {len(erros)}")
print(f"Resumo salvo em:       {resumo_path}")
