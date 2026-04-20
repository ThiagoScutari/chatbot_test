"""
Extrai dados de um post do Instagram pelo shortcode da URL.
Exemplo de URL: https://www.instagram.com/p/DXRujy6kRkn/
Shortcode: DXRujy6kRkn
"""
import json
import os
import instaloader

SHORTCODE = "DXRujy6kRkn"
PASTA_SAIDA = "dados_instagram"

os.makedirs(PASTA_SAIDA, exist_ok=True)

loader = instaloader.Instaloader(
    download_pictures=True,
    download_videos=False,
    download_video_thumbnails=False,
    download_comments=False,
    save_metadata=False,
    post_metadata_txt_pattern="",   # não gera .txt automático
    dirname_pattern=PASTA_SAIDA,
)

print(f"Extraindo post: {SHORTCODE}")
post = instaloader.Post.from_shortcode(loader.context, SHORTCODE)

# Coleta os dados estruturados
dados = {
    "shortcode":   post.shortcode,
    "url":         f"https://www.instagram.com/p/{post.shortcode}/",
    "perfil":      post.owner_username,
    "data":        post.date_utc.strftime("%Y-%m-%d %H:%M:%S"),
    "curtidas":    post.likes,
    "legenda":     post.caption,
    "hashtags":    list(post.caption_hashtags),
    "imagens":     [],
}

# Se for carrossel (múltiplas imagens), coleta todas as URLs
if post.typename == "GraphSidecar":
    for node in post.get_sidecar_nodes():
        dados["imagens"].append(node.display_url)
else:
    dados["imagens"].append(post.url)

# Salva JSON
caminho_json = os.path.join(PASTA_SAIDA, f"{SHORTCODE}.json")
with open(caminho_json, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=2)

# Baixa as imagens
loader.download_post(post, target=PASTA_SAIDA)

print(f"\n--- Dados extraídos ---")
print(f"Perfil:   @{dados['perfil']}")
print(f"Data:     {dados['data']}")
print(f"Curtidas: {dados['curtidas']}")
print(f"Imagens:  {len(dados['imagens'])}")
print(f"Legenda:\n{dados['legenda']}")
print(f"\nJSON salvo em: {caminho_json}")
