"""Analyze Camisart Instagram posts and generate consolidated report."""
import glob
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = r'C:\workspace\chatbot\test\dados_instagram\camisart_belem'
OUTPUT = r'C:\workspace\chatbot\docs\instagram_analysis.md'


def load_posts():
    files = sorted(glob.glob(os.path.join(BASE, '*.json')))
    posts = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                posts.append(json.load(fp))
        except Exception as e:
            print(f'ERR loading {f}: {e}', file=sys.stderr)
    return posts


# Category keyword maps (lowercase). Each post can match multiple categories.
CATEGORY_KEYWORDS = {
    'Polo': ['polo', 'piquet', 'piquê', 'gola'],
    'Camiseta': ['camiseta', 't-shirt', 'tshirt', 'baby look', 'babylook', 'camosa'],
    'Regata': ['regata', 'machão', 'machao', 'sem manga'],
    'Jaleco': ['jaleco', 'scrub', 'hospitalar', 'médico', 'medico', 'enfermagem',
               'enfermeir', 'saúde', 'saude', 'clínica', 'clinica'],
    'Uniforme': ['uniforme', 'epi', 'industrial', 'fardamento', 'farda',
                 'corporativo', 'empresa'],
    'Acessórios': ['boné', 'bone', 'touca', 'máscara', 'mascara', 'sacola',
                   'ecobag', 'avental', 'mochila', 'bolsa'],
    'Temáticos': ['temátic', 'tematic', 'evento', 'tema ', 'festa', 'comemorativ',
                  'dia das mães', 'dia das maes', 'halloween', 'festa junina',
                  'natal', 'páscoa', 'pascoa', 'carnaval', 'dia dos pais',
                  'black friday', 'aniversário', 'aniversario', 'formatura'],
    'Institucional/outros': [],  # fallback
}

INSTITUTIONAL_HINTS = [
    'feriado', 'bom dia', 'boa tarde', 'boa noite', 'feliz', 'parabéns',
    'parabens', 'horário', 'horario', 'fechado', 'aberto', 'reabertura',
    'frase', 'reflexão', 'reflexao', 'motivacional', 'segunda-feira',
    'sexta-feira', 'fim de semana', 'feliz dia', 'gratidão', 'gratidao',
]

MATERIAL_KEYWORDS = [
    'piquet', 'piquê', 'algodão', 'algodao', 'pv', 'poliéster', 'poliester',
    'gabardine', 'dry-fit', 'dry fit', 'dryfit', 'malha fria', 'helanca',
    'oxford', 'brim', 'sarja', 'cotton', 'viscose', 'linho', 'tactel',
    'microfibra', 'malha pp',
]

CUSTOMIZATION_KEYWORDS = [
    'bordado', 'bordada', 'bordar', 'bordando',
    'serigrafia', 'serigráfica',
    'sublimação', 'sublimacao', 'sublimad',
    'silk', 'silkscreen',
    'estampa', 'estampad',
    'transfer', 'dtf',
    'personaliz',
]

AUDIENCE_KEYWORDS = [
    'saúde', 'saude', 'hospitalar', 'corporativo', 'empresarial',
    'escolar', 'escola', 'esport', 'igreja', 'evangélic', 'evangelic',
    'evento', 'industrial', 'fábrica', 'fabrica', 'restaurant',
    'condomínio', 'condominio', 'igreja', 'time', 'turma',
]

PRICE_REGEX = re.compile(r'R\$\s*[\d]+(?:[.,]\d+)*', re.IGNORECASE)
HASHTAG_REGEX = re.compile(r'#\w+', re.UNICODE)

SALES_PHRASES_PATTERNS = [
    r'garanta\s+já\b', r'garanta\s+ja\b', r'encomende\b', r'encomendas?\b',
    r'personalizamos\b', r'fa[çc]a\s+seu\s+or[çc]amento',
    r'or[çc]amento', r'fale\s+conosco', r'entre\s+em\s+contato',
    r'whats(app)?\b', r'estamos\s+localizad', r'venha\s+conferir',
    r'aceitamos\s+encomendas?', r'pre[çc]o\s+especial',
    r'promo[çc][ãa]o', r'desconto', r'frete\s+gr[áa]tis',
    r'pronta\s+entrega', r'sob\s+encomenda', r'fa[çc]a\s+j[áa]', r'aproveite',
]


def detect_categories(legenda_lower):
    cats = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        if cat == 'Institucional/outros':
            continue
        for kw in kws:
            if kw in legenda_lower:
                cats.append(cat)
                break
    if not cats:
        # check institutional
        for hint in INSTITUTIONAL_HINTS:
            if hint in legenda_lower:
                return ['Institucional/outros']
        return ['Institucional/outros']
    return cats


def find_keywords(text_lower, keywords):
    found = []
    for kw in keywords:
        if kw in text_lower:
            found.append(kw)
    return found


def find_sales_phrases(text_lower):
    found = []
    for pat in SALES_PHRASES_PATTERNS:
        m = re.search(pat, text_lower, re.IGNORECASE)
        if m:
            found.append(m.group(0))
    return found


def main():
    posts = load_posts()
    print(f'Loaded {len(posts)} posts')

    # Index by category
    by_category = defaultdict(list)
    all_prices = Counter()
    all_materials = Counter()
    all_customizations = Counter()
    all_audiences = Counter()
    all_hashtags_global = Counter()
    all_sales_phrases = Counter()
    posts_without_hashtags = 0
    posts_without_price = 0

    for p in posts:
        leg = p.get('legenda', '') or ''
        leg_l = leg.lower()
        cats = detect_categories(leg_l)
        for c in cats:
            by_category[c].append(p)

        # globals
        prices = PRICE_REGEX.findall(leg)
        if prices:
            for pr in prices:
                # normalize
                norm = re.sub(r'\s+', ' ', pr.strip())
                all_prices[norm] += 1
        else:
            posts_without_price += 1

        for m in find_keywords(leg_l, MATERIAL_KEYWORDS):
            all_materials[m] += 1
        for c in find_keywords(leg_l, CUSTOMIZATION_KEYWORDS):
            all_customizations[c] += 1
        for a in find_keywords(leg_l, AUDIENCE_KEYWORDS):
            all_audiences[a] += 1
        for sp in find_sales_phrases(leg_l):
            all_sales_phrases[sp.lower()] += 1

        hashtags = p.get('hashtags') or []
        if not hashtags:
            # try to extract from caption
            extracted = HASHTAG_REGEX.findall(leg)
            if extracted:
                hashtags = extracted
        if not hashtags:
            posts_without_hashtags += 1
        for h in hashtags:
            all_hashtags_global[h.lower()] += 1

    # Build report
    dates = sorted([p.get('data', '') for p in posts if p.get('data')])
    total_likes = sum(p.get('curtidas', 0) for p in posts)
    period = f"{dates[0]} a {dates[-1]}" if dates else 'desconhecido'

    lines = []
    lines.append('# Análise de Posts Instagram — Camisart Belém\n')
    lines.append('> Gerado em 2026-04-27')
    lines.append('> Fonte: test/dados_instagram/camisart_belem/\n')

    lines.append('## Nota sobre estrutura\n')
    lines.append(
        'A análise original previa subpastas categorizadas (`1-Polo/`, `2-Camiseta/`, etc.), '
        'mas o diretório é flat: ~192 JSONs (formato shortcode Instagram, ex: `DXRujy6kRkn.json`) '
        'e ~199 imagens `*.jpg` (formato datetime) na raiz, **sem correlação 1:1 por nome**. '
        'A subpasta `comentarios/` foi ignorada nesta análise. '
        'A categorização foi feita por inferência do conteúdo da legenda (palavras-chave). '
        'Um post pode aparecer em mais de uma categoria.\n'
    )

    lines.append('## Resumo\n')
    lines.append(f'- Total de posts JSON analisados: **{len(posts)}**')
    lines.append(f'- Período coberto: **{period}**')
    lines.append(f'- Total de curtidas somadas: **{total_likes}**')
    lines.append(f'- Posts sem hashtags (após varredura na legenda): **{posts_without_hashtags}** ({posts_without_hashtags*100//max(len(posts),1)}%)')
    lines.append(f'- Posts sem preço mencionado: **{posts_without_price}** ({posts_without_price*100//max(len(posts),1)}%)')
    lines.append('- Categorias inferidas:')
    for cat in CATEGORY_KEYWORDS.keys():
        lines.append(f'  - {cat}: {len(by_category.get(cat, []))} posts')
    lines.append('')

    lines.append('## Por Categoria\n')

    for cat in CATEGORY_KEYWORDS.keys():
        cat_posts = by_category.get(cat, [])
        lines.append(f'### {cat}\n')
        lines.append(f'**Posts analisados:** {len(cat_posts)}\n')

        # category-specific aggregates
        cat_prices = Counter()
        cat_materials = Counter()
        cat_custom = Counter()
        cat_audience = Counter()
        cat_hashtags = Counter()
        cat_sales = Counter()

        for p in cat_posts:
            leg = p.get('legenda', '') or ''
            leg_l = leg.lower()
            for pr in PRICE_REGEX.findall(leg):
                cat_prices[re.sub(r'\s+', ' ', pr.strip())] += 1
            for m in find_keywords(leg_l, MATERIAL_KEYWORDS):
                cat_materials[m] += 1
            for c in find_keywords(leg_l, CUSTOMIZATION_KEYWORDS):
                cat_custom[c] += 1
            for a in find_keywords(leg_l, AUDIENCE_KEYWORDS):
                cat_audience[a] += 1
            for sp in find_sales_phrases(leg_l):
                cat_sales[sp.lower()] += 1
            hashtags = p.get('hashtags') or HASHTAG_REGEX.findall(leg)
            for h in hashtags:
                cat_hashtags[h.lower()] += 1

        if cat_prices:
            lines.append('**Preços mencionados:** ' +
                         ', '.join(f'{p} ({n}x)' for p, n in cat_prices.most_common(20)))
        else:
            lines.append('**Preços mencionados:** _nenhum_')
        if cat_materials:
            lines.append('**Materiais citados:** ' +
                         ', '.join(f'{m} ({n}x)' for m, n in cat_materials.most_common(15)))
        else:
            lines.append('**Materiais citados:** _nenhum_')
        if cat_custom:
            lines.append('**Personalizações:** ' +
                         ', '.join(f'{c} ({n}x)' for c, n in cat_custom.most_common(15)))
        else:
            lines.append('**Personalizações:** _nenhuma_')
        if cat_audience:
            lines.append('**Público-alvo:** ' +
                         ', '.join(f'{a} ({n}x)' for a, n in cat_audience.most_common(10)))
        else:
            lines.append('**Público-alvo:** _não identificado_')
        if cat_hashtags:
            lines.append('**Hashtags top 10:** ' +
                         ', '.join(f'{h} ({n})' for h, n in cat_hashtags.most_common(10)))
        else:
            lines.append('**Hashtags top 10:** _nenhuma_')
        if cat_sales:
            lines.append('**Frases de venda recorrentes:**')
            for sp, n in cat_sales.most_common(5):
                lines.append(f'- "{sp}" ({n}x)')
        else:
            lines.append('**Frases de venda recorrentes:** _nenhuma identificada_')

        lines.append('\n**Captions completas:**\n')
        # sort by date
        sorted_posts = sorted(cat_posts, key=lambda x: x.get('data', ''))
        for i, p in enumerate(sorted_posts, 1):
            data = p.get('data', '?')
            sc = p.get('shortcode', '?')
            curt = p.get('curtidas', 0)
            leg = (p.get('legenda', '') or '').strip()
            lines.append(f'{i}. **{data}** — `{sc}` ({curt} curtidas)')
            if leg:
                # quote each line
                for ln in leg.split('\n'):
                    lines.append(f'   > {ln}')
            else:
                lines.append('   > _(sem legenda)_')
            lines.append('')

        lines.append('')

    # Top hashtags global
    lines.append('## Top hashtags globais\n')
    if all_hashtags_global:
        lines.append('| Hashtag | Frequência |')
        lines.append('|---|---|')
        for h, n in all_hashtags_global.most_common(30):
            lines.append(f'| {h} | {n} |')
    else:
        lines.append('_Nenhuma hashtag identificada nos posts._')
    lines.append('')

    # Top prices global
    lines.append('## Top preços (global)\n')
    if all_prices:
        lines.append('| Preço | Ocorrências |')
        lines.append('|---|---|')
        for p, n in all_prices.most_common(20):
            lines.append(f'| {p} | {n} |')
    else:
        lines.append('_Nenhum preço identificado._')
    lines.append('')

    # Top materials global
    lines.append('## Top materiais (global)\n')
    if all_materials:
        lines.append('| Material | Ocorrências |')
        lines.append('|---|---|')
        for m, n in all_materials.most_common(15):
            lines.append(f'| {m} | {n} |')
    lines.append('')

    # Top customizations global
    lines.append('## Top personalizações (global)\n')
    if all_customizations:
        lines.append('| Técnica | Ocorrências |')
        lines.append('|---|---|')
        for c, n in all_customizations.most_common(15):
            lines.append(f'| {c} | {n} |')
    lines.append('')

    # Top audiences global
    lines.append('## Top públicos-alvo (global)\n')
    if all_audiences:
        lines.append('| Público | Ocorrências |')
        lines.append('|---|---|')
        for a, n in all_audiences.most_common(15):
            lines.append(f'| {a} | {n} |')
    lines.append('')

    # Lacunas
    lines.append('## Lacunas identificadas\n')
    lines.append(f'- **Posts sem hashtags:** {posts_without_hashtags} de {len(posts)} '
                 f'({posts_without_hashtags*100//max(len(posts),1)}%) — limita SEO/descoberta '
                 'e dificulta categorização automática futura.')
    lines.append(f'- **Posts sem preço explícito:** {posts_without_price} de {len(posts)} '
                 f'({posts_without_price*100//max(len(posts),1)}%) — preços geralmente vivem '
                 'na imagem ou no DM, não na legenda.')
    sparse = [c for c in CATEGORY_KEYWORDS if len(by_category.get(c, [])) < 5]
    if sparse:
        lines.append(f'- **Categorias com poucos dados (<5 posts):** {", ".join(sparse)}.')
    lines.append('- **Limitação de imagens:** ~199 imagens JPG estão na raiz mas '
                 '**não compartilham nome com os JSONs** (timestamp vs shortcode). '
                 'Informações visuais (cores disponíveis, modelos, exemplos de bordado) '
                 'não foram extraídas — exigiria OCR / vision model para enriquecer.')
    lines.append('- **Subpasta `comentarios/`** não foi processada — pode conter '
                 'perguntas frequentes do público (FAQ real) úteis para o chatbot.')
    lines.append('- **Inferência de categoria por legenda** é ruidosa: posts curtos '
                 'sem palavra-chave caem em `Institucional/outros`, mesmo que mostrem produto.')
    lines.append('')

    # Recommendations
    lines.append('## Recomendações para a base de conhecimento\n')
    lines.append('Baseado nos achados, sugestões para enriquecer `camisart_knowledge_base.md` '
                 'e/ou `products.json`:\n')
    lines.append('1. **Catálogo de materiais oficial** — consolidar a lista de tecidos '
                 'efetivamente vendidos (top materiais da análise) com descrição, '
                 'gramatura e indicação de uso. Hoje a legenda menciona poucos materiais '
                 'de forma esparsa.')
    lines.append('2. **Tabela de personalizações** — bordado, sublimação, serigrafia, DTF: '
                 'descrever processo, lead time típico e quando cada técnica se aplica. '
                 'Frequência alta destas palavras na análise confirma demanda.')
    lines.append('3. **FAQ de preços** — como praticamente nenhuma legenda traz preço, '
                 'o bot precisa de tabela de faixas de preço por produto/quantidade '
                 'para responder direto, sem encaminhar 100% dos casos para humano.')
    lines.append('4. **Públicos-alvo / nichos** — criar fluxos específicos por nicho '
                 '(saúde, corporativo, escolar, igreja, esporte) já que apareceram '
                 'recorrentemente nas legendas.')
    lines.append('5. **Frases de chamada institucionais** — reaproveitar frases de venda '
                 'recorrentes (ex.: "encomende já", "personalizamos") como tom de voz '
                 'do chatbot, alinhando com a comunicação atual da marca.')
    lines.append('6. **Processar `comentarios/`** num próximo enriquecimento — fonte '
                 'natural de perguntas frequentes reais (preço, prazo, tamanhos) para '
                 'o `faq.json`.')
    lines.append('7. **OCR/Vision nas imagens** — sprint futura: extrair preços, tabelas '
                 'de tamanho e cores das ~199 imagens, que claramente concentram '
                 'as informações comerciais que faltam nas legendas.')
    lines.append('')

    out = '\n'.join(lines)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as fp:
        fp.write(out)

    # Stdout summary
    print('\n=== SUMMARY ===')
    print(f'Total posts: {len(posts)}')
    print(f'Period: {period}')
    print(f'Total likes: {total_likes}')
    print('Distribution:')
    for cat in CATEGORY_KEYWORDS:
        print(f'  {cat}: {len(by_category.get(cat, []))}')
    print('Top 5 prices:', all_prices.most_common(5))
    print('Top 5 materials:', all_materials.most_common(5))
    print('Top 5 hashtags:', all_hashtags_global.most_common(5))
    print('Top 5 customizations:', all_customizations.most_common(5))
    print(f'Output: {OUTPUT}')
    print(f'Output size: {os.path.getsize(OUTPUT)} bytes ({os.path.getsize(OUTPUT)//1024} KB)')


if __name__ == '__main__':
    main()
