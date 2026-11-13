#!/usr/bin/env python3
"""作品与记录 —— 静态站点构建脚本

用法：
    python3 build.py            # 构建到 _site/
    python3 build.py --serve    # 构建后本地预览 http://127.0.0.1:8777

目录约定：
- src/base.html        页面骨架（head / header / footer）
- src/pages/*.html     静态页面片段（案例页、列表页外壳）
- content/thinking/    思考文章（Markdown + front matter）
- content/research/    研究长文（Markdown）与研究卡片（Markdown / cards.json）
- content/reading/     读书条目（books.json）
- assets/              样式、脚本、图片
- 构建产物输出到 _site/，由 GitHub Actions 发布到 GitHub Pages
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import pathlib
import re
import shutil
import socketserver
import sys
import http.server

try:
    import markdown  # type: ignore
except ImportError:  # 本地未装时给出手动路径
    markdown = None

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
PAGES_DIR = SRC / "pages"
CONTENT = ROOT / "content"
PUB = ROOT / "_site"
ASSETS = ROOT / "assets"

SITE_URL = "https://zhaolijian.github.io"
SITE_NAME = "作品与记录"
YEAR = dt.date.today().year

NAV = [
    ("home", "/", "首页"),
    ("cases", "/#cases", "作品"),
    ("thinking", "/thinking.html", "思考"),
    ("reading", "/reading.html", "读书"),
    ("research", "/research.html", "研究"),
    ("map", "/map.html", "地图"),
    ("repos", "/#repos", "开源"),
]

# 静态页面：只保留案例页；列表页由构建脚本生成
STATIC_PAGES = [
    dict(out="cases/geo.html", nav="cases", title="源引 GEO 案例", desc="源引 GEO：面向中小企业的生成式引擎优化产品——品牌诊断、内容 Agent 与真人探针回测。"),
    dict(out="cases/yueji.html", nav="cases", title="阅记案例", desc="阅记：把纸质书划线句变成可复习知识结构的笔记助手——拍照识别、结构化整理、思维导图与导出。"),
    dict(out="cases/platform.html", nav="cases", title="B 端产品与中台案例", desc="B 端产品与中台的产品化：权限与字段方案、动态配置 / 流控 / 消息队列中台的 Web 化改造。"),
    dict(out="cases/opc.html", nav="cases", title="AI 产品 0→1 实验案例", desc="三款 AI C 端产品的 MVP 实验：用最低成本验证，再决定是否继续。"),
    dict(out="cases/robot-duck.html", nav="cases", title="机器鸭复刻实验", desc="机器鸭：零基础复刻一台 25cm 双足机器人——先在 MuJoCo 仿真里跑通 7 个官方策略与 600+ 次压力测试，再决定是否进入真机阶段。"),
    dict(out="map.html", nav="map", title="主题地图", desc="把书、文章、研究、项目串成五条线：用户与需求、发现与验证、增长与商业、判断与决策、学习与长期主义。"),
]


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------
def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    block = text[4:end]
    body = text[end + 5:]
    meta: dict = {}
    links: list[dict] = []
    current_list = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - "):
            item = line[4:].strip()
            if "｜" in item:
                label, url = item.rsplit("｜", 1)
                links.append({"label": label.strip(), "url": url.strip()})
            elif current_list is not None:
                links.append({"label": item, "url": ""})
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value == "":
                current_list = key
                meta[key] = []
                continue
            meta[key] = value
            current_list = None
    if links:
        meta["links"] = links
    return meta, body


def md_to_html(text: str) -> str:
    if markdown is None:
        raise SystemExit("需要 markdown 库：pip install markdown（或设置 PYTHONPATH=tools/pylibs）")
    return markdown.markdown(text, extensions=["extra", "sane_lists"])


def text_of_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return htmllib.unescape(text).strip()


def word_count(fragment: str) -> int:
    return len(re.sub(r"\s+", "", text_of_html(fragment)))


def escape_attr(value: str) -> str:
    return htmllib.escape(value or "", quote=True)


def load_collection(folder: pathlib.Path) -> list[dict]:
    items = []
    if not folder.exists():
        return items
    for path in sorted(folder.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = split_front_matter(raw)
        meta["slug"] = path.stem
        meta["_body"] = body
        meta["_path"] = path
        items.append(meta)
    return items


def render_links(links: list[dict], title: str = "参考链接") -> str:
    if not links:
        return ""
    rows = []
    for link in links:
        label = escape_attr(link.get("label", ""))
        url = escape_attr(link.get("url", ""))
        if not url:
            rows.append(f"<li>{label}</li>")
        else:
            rows.append(f'<li><a href="{url}" target="_blank" rel="noopener">{label}</a></li>')
    return f'<div class="article-links"><h2>{title}</h2><ul>' + "".join(rows) + "</ul></div>"


# ---------------------------------------------------------------------------
# 各类页面生成
# ---------------------------------------------------------------------------
def article_page(item: dict) -> tuple[str, str]:
    """返回 (输出路径, HTML 正文片段)。"""
    slug = item["slug"]
    date = item.get("date", "")
    title = item.get("title", slug)
    fmt = item.get("format", "markdown")
    body = item["_body"]
    body_html = body if fmt == "html" else md_to_html(body)
    tags = item.get("tags", "")
    words = word_count(body_html)
    source = item.get("source", "")
    links_html = render_links(item.get("links", []))
    source_html = f'<p class="article-note">{htmllib.escape(source) if source.startswith("素材") else "素材：" + htmllib.escape(source)}</p>' if source else ""
    content = f"""<div class="article">
  <div class="wrap">
    <div class="prose">
      <p class="eyebrow">产品思考{f" · {htmllib.escape(tags)}" if tags else ""}</p>
      <h1>{htmllib.escape(title)}</h1>
      <p class="article-meta">{htmllib.escape(date)} · 约 {words} 字</p>
{body_html}
{links_html}
{source_html}
    </div>
  </div>
</div>"""
    return f"thinking/{slug}.html", content


def research_page(item: dict) -> tuple[str, str]:
    slug = item["slug"]
    title = item.get("title", slug)
    date = item.get("date", "")
    topic = item.get("topic", "研究")
    fmt = item.get("format", "markdown")
    body = item["_body"]
    body_html = body if fmt == "html" else md_to_html(body)
    words = word_count(body_html)
    links_html = render_links(item.get("links", []), "来源与参考")
    source = item.get("source", "")
    source_html = f'<p class="article-note">{htmllib.escape(source)}</p>' if source else ""

    # 从 h2 生成目录
    toc = re.findall(r"<h2[^>]*>(.*?)</h2>", body_html, re.S)
    toc_html = "".join(f'<li><a href="#sec-{i}">{text_of_html(t)}</a></li>' for i, t in enumerate(toc, 1))
    for i in range(len(toc), 0, -1):
        pass
    # 给 h2 加锚点（按顺序）
    counter = {"n": 0}

    def add_id(m):
        counter["n"] += 1
        return f'<h2 id="sec-{counter["n"]}">{m.group(1)}</h2>'

    body_html = re.sub(r"<h2[^>]*>(.*?)</h2>", add_id, body_html, flags=re.S)
    toc_block = f'<aside class="longread-toc"><p class="eyebrow">目录</p><ol>{toc_html}</ol></aside>' if toc else ""

    content = f"""<div class="article longread">
  <div class="wrap longread-wrap{" has-toc" if toc else ""}">
    {toc_block}
    <div class="prose">
      <p class="eyebrow">研究 · {htmllib.escape(topic)}</p>
      <h1>{htmllib.escape(title)}</h1>
      <p class="article-meta">{htmllib.escape(date)} · 约 {words} 字 · <a href="/research.html">← 返回研究列表</a></p>
{body_html}
{links_html}
{source_html}
    </div>
  </div>
</div>"""
    return f"research/{slug}.html", content


def deep_note_page(item: dict) -> tuple[str, str]:
    """读书深读笔记页：长文布局 + 目录。"""
    slug = item["slug"]
    title = item.get("title", slug)
    book = item.get("book", "")
    author = item.get("author", "")
    date = item.get("date", "")
    fmt = item.get("format", "markdown")
    body = item["_body"]
    body_html = body if fmt == "html" else md_to_html(body)
    words = word_count(body_html)
    links_html = render_links(item.get("links", []), "相关")
    toc = re.findall(r"<h2[^>]*>(.*?)</h2>", body_html, re.S)
    toc_html = "".join(f'<li><a href="#sec-{i}">{text_of_html(t)}</a></li>' for i, t in enumerate(toc, 1))
    counter = {"n": 0}

    def add_id(m):
        counter["n"] += 1
        return f'<h2 id="sec-{counter["n"]}">{m.group(1)}</h2>'

    body_html = re.sub(r"<h2[^>]*>(.*?)</h2>", add_id, body_html, flags=re.S)
    toc_block = f'<aside class="longread-toc"><p class="eyebrow">目录</p><ol>{toc_html}</ol></aside>' if toc else ""
    meta = " · ".join(x for x in [book, author] if x)
    content = f"""<div class="article longread reading-note">
  <div class="wrap longread-wrap{" has-toc" if toc else ""}">
    {toc_block}
    <div class="prose">
      <p class="eyebrow">读书笔记 · 深读</p>
      <h1 class="note-h1">{htmllib.escape(title)}</h1>
      <p class="article-meta">{htmllib.escape(meta)} · {htmllib.escape(date)} · 约 {words} 字 · <a href="/reading.html">← 返回读书笔记</a></p>
{body_html}
{links_html}
    </div>
  </div>
</div>"""
    return f"reading/{slug}.html", content


def deep_card_html(item: dict) -> str:
    slug = item["slug"]
    title = item.get("title", "")
    book = item.get("book", "")
    author = item.get("author", "")
    summary = item.get("summary", "")
    return f"""<div class="book deep-card">
  <span class="cat">深读笔记</span>
  <h3><a href="/reading/{escape_attr(slug)}.html">{htmllib.escape(title)}</a></h3>
  <p class="muted">{htmllib.escape(book)} · {htmllib.escape(author)}</p>
  <p>{htmllib.escape(summary)}</p>
  <a class="more" href="/reading/{escape_attr(slug)}.html">读深读笔记 →</a>
</div>"""


def card_html(card: dict) -> str:
    topic = escape_attr(card.get("topic", ""))
    title = escape_attr(card.get("title", ""))
    summary = card.get("summary", "")
    data = card.get("data", "")
    judgment = card.get("judgment", "")
    link = card.get("link", "")
    related = card.get("related", "")
    actions = []
    if link:
        actions.append(f'<a class="more" href="{escape_attr(link)}">读全文 →</a>')
    elif related:
        actions.append(f'<a class="more" href="/research/{escape_attr(related)}.html">读全文 →</a>')
    return f"""<div class="book research-card">
  <span class="cat">{topic}</span>
  <h3>{title}</h3>
  <p>{summary}</p>
  <p class="muted" style="font-size:.8rem">数据口径：{data}</p>
  <div class="takeaway">{judgment}</div>
  {''.join(actions)}
</div>"""


def essay_html(item: dict) -> str:
    slug = item["slug"]
    title = escape_attr(item.get("title", slug))
    summary = item.get("summary", "")
    date = item.get("date", "")
    tags = item.get("tags", "")
    tag_html = "".join(f'<span class="tag">{escape_attr(t.strip())}</span>' for t in re.split(r"[,，]", tags) if t.strip())
    return f"""<a class="essay" href="/thinking/{slug}.html">
  <div class="date">{escape_attr(date)}</div>
  <div>
    <h3>{title}</h3>
    <p>{summary}</p>
    <div class="essay-tags">{tag_html}</div>
  </div>
</a>"""


def book_html(book: dict) -> str:
    note = book.get("note", "")
    note_link = f'<a class="more" href="/reading/{escape_attr(note)}.html">深读笔记 →</a>' if note else ""
    return f"""<div class="book">
  <span class="cat">{escape_attr(book.get("cat", ""))}</span>
  <h3>{escape_attr(book.get("title", ""))}</h3>
  <p class="muted">{escape_attr(book.get("author", ""))}</p>
  <p>{book.get("body", "")}</p>
  <div class="takeaway">{book.get("takeaway", "")}</div>
  {note_link}
</div>"""


def build() -> None:
    if PUB.exists():
        shutil.rmtree(PUB)
    PUB.mkdir(parents=True, exist_ok=True)

    shutil.copytree(ASSETS, PUB / "assets", dirs_exist_ok=True)
    (PUB / ".nojekyll").write_text("", encoding="utf-8")

    base = (SRC / "base.html").read_text(encoding="utf-8")

    def nav_html(active: str) -> str:
        items = []
        for key, href, label in NAV:
            current = ' aria-current="page"' if key == active else ""
            items.append(f'      <a href="{href}"{current}>{label}</a>')
        items.append('      <a class="nav-cta" href="https://github.com/zhaolijian" target="_blank" rel="noopener">GitHub</a>')
        return "\n".join(items)

    def fill(tpl: str, mapping: dict) -> str:
        for key, value in mapping.items():
            tpl = tpl.replace("{{" + key + "}}", value)
            tpl = tpl.replace("<!--" + key + "-->", value)
        return tpl

    def write_page(out: str, nav: str, title: str, desc: str, body: str) -> None:
        dest = PUB / out
        dest.parent.mkdir(parents=True, exist_ok=True)
        canonical = f"{SITE_URL}/" if out == "index.html" else f"{SITE_URL}/{out}"
        html = fill(base, dict(
            title=title,
            og_title=title,
            description=desc,
            canonical=canonical,
            nav=nav_html(nav),
            content=body,
            year=str(YEAR),
        ))
        dest.write_text(html, encoding="utf-8")
        print(f"[ok] {out}")

    # ---- 读取内容 ----
    essays = load_collection(CONTENT / "thinking")
    essays.sort(key=lambda x: (x.get("date", ""), x["slug"]), reverse=True)
    research_items = load_collection(CONTENT / "research")
    longreads = [i for i in research_items if i.get("kind") == "longread"]
    cards = [i for i in research_items if i.get("kind") == "card"]
    cards_json = CONTENT / "research" / "cards.json"
    if cards_json.exists():
        cards = json.loads(cards_json.read_text(encoding="utf-8")) + cards
    books_data = CONTENT / "reading" / "books.json"
    books_meta = json.loads(books_data.read_text(encoding="utf-8")) if books_data.exists() else {}
    groups = books_meta.get("groups", [])
    group_intros = books_meta.get("group_intros", {})
    books_new = CONTENT / "reading" / "books-new.json"
    if books_new.exists():
        extra = json.loads(books_new.read_text(encoding="utf-8"))
        by_group = {g["group"]: g for g in groups}
        for book in extra:
            gname = book.get("group", "其他")
            by_group.setdefault(gname, {"group": gname, "books": []})["books"].append(book)
        groups = list(by_group.values())
    # 合并同名分组 + 固定展示顺序
    merged: dict[str, dict] = {}
    for g in groups:
        name = "长期主义与人物" if g["group"] == "长期主义" else g["group"]
        merged.setdefault(name, {"group": name, "books": []})["books"].extend(g["books"])
    order = ["产品与用户", "商业、增长与思维", "商业与金融", "个人成长", "沟通表达", "长期主义与人物"]
    groups = [merged[k] for k in order if k in merged] + [g for k, g in merged.items() if k not in order]

    # 长文按日期倒序
    longreads.sort(key=lambda x: (x.get("date", ""), x["slug"]), reverse=True)
    # 读书深读笔记（固定顺序：产品 → 思维/学习 → 成长 → 投资）
    reading_notes = load_collection(CONTENT / "reading" / "notes")
    note_order = ["inspired", "yujun-product-method", "six-hats", "feynman-technique",
                  "cognitive-awakening", "flowering-life", "simplest-investing", "duan-yongping-quotes"]
    reading_notes.sort(key=lambda x: note_order.index(x["slug"]) if x["slug"] in note_order else 99)


    # ---- 文章页 ----
    for item in essays:
        out, body = article_page(item)
        write_page(out, "thinking", f'{item.get("title", "")}｜{SITE_NAME}', item.get("summary", ""), body)

    # ---- 研究长文页 ----
    for item in longreads:
        out, body = research_page(item)
        write_page(out, "research", f'{item.get("title", "")}｜{SITE_NAME}', item.get("summary", ""), body)

    # ---- 读书深读笔记页 ----
    for item in reading_notes:
        out, body = deep_note_page(item)
        write_page(out, "reading", f'{item.get("title", "")}｜{SITE_NAME}', item.get("summary", ""), body)

    # ---- 静态案例页 ----
    for page in STATIC_PAGES:
        out = page["out"]
        src = PAGES_DIR / out
        body = src.read_text(encoding="utf-8") if src.exists() else ""
        write_page(out, page["nav"], f'{page["title"]}｜{SITE_NAME}', page["desc"], body)

    # ---- 列表页 ----
    thinking_shell = (PAGES_DIR / "thinking.html").read_text(encoding="utf-8")
    write_page("thinking.html", "thinking", f"产品思考｜{SITE_NAME}",
               "关于 AI 产品、GEO、Agent 工作流、需求判断、0→1 验证与 B 端产品化的思考。",
               fill(thinking_shell, {"ESSAY_LIST": "\n      ".join(essay_html(e) for e in essays)}))

    research_shell = (PAGES_DIR / "research.html").read_text(encoding="utf-8")
    longread_entries = []
    card_related = {"技术不是瓶颈，验收标准才是": "ai-education", "份额之争，首先是口径之争": "browser-share"}
    for card in cards:
        card = dict(card)
        card.setdefault("related", card_related.get(card.get("title", ""), ""))
        longread_entries.append(card_html(card))
    longread_list = "".join(
        f'<a class="essay" href="/research/{i["slug"]}.html"><div class="date">{escape_attr(i.get("date",""))}</div>'
        f'<div><h3>{escape_attr(i.get("title",""))}</h3><p>{i.get("summary","")}</p>'
        f'<div class="essay-tags"><span class="tag">{escape_attr(i.get("topic",""))}</span></div></div></a>'
        for i in longreads
    )
    write_page("research.html", "research", f"行业研究｜{SITE_NAME}",
               "用研究支持判断，而不是用研究代替判断：主题卡片、调研长文与方法论。",
               fill(research_shell, {
                   "RESEARCH_CARDS": "\n      ".join(longread_entries),
                   "LONGREADS": longread_list,
               }))

    reading_shell = (PAGES_DIR / "reading.html").read_text(encoding="utf-8")
    groups_html = []
    for group in groups:
        intro = group_intros.get(group["group"], "")
        intro_html = f'\n<p class="group-intro">{htmllib.escape(intro)}</p>' if intro else ""
        groups_html.append(
            f'<div class="book-group">\n<h2>{escape_attr(group["group"])}</h2>{intro_html}\n<div class="book-grid">\n'
            + "\n".join(book_html(b) for b in group["books"])
            + "\n</div>\n</div>"
        )
    deep_html = "\n      ".join(deep_card_html(n) for n in reading_notes)
    book_count = sum(len(g["books"]) for g in groups)
    write_page("reading.html", "reading", f"读书笔记｜{SITE_NAME}",
               f"{book_count} 本书：{len(reading_notes)} 篇深读笔记与全书目卡片，记录书的结构、能改变判断的结论与适用边界。",
               fill(reading_shell, {
                   "DEEP_NOTES": deep_html,
                   "BOOK_GROUPS": "\n\n    ".join(groups_html),
               }))

    # ---- 首页 ----
    index_shell = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    thinking_preview = "\n      ".join(essay_html(e) for e in essays[:5])
    research_preview = "\n      ".join(card_html(dict(c, related=card_related.get(c.get("title", ""), ""))) for c in cards[:4])
    deep_books = [b for g in groups for b in g["books"] if b.get("note")]
    selected_books = (deep_books[:3] or [b for g in groups for b in g["books"]][:3])
    books_preview = "\n      ".join(book_html(b) for b in selected_books)
    write_page("index.html", "home",
               f"{SITE_NAME}｜作品、思考、读书与研究",
               "个人作品与记录：做过的产品、想清楚的问题、读过的书和做过的研究。",
               fill(index_shell, {
                   "THINKING_PREVIEW": thinking_preview,
                   "RESEARCH_PREVIEW": research_preview,
                   "READING_PREVIEW": books_preview,
               }))

    # ---- 404 ----
    four = """<section class="section"><div class="wrap" style="padding-top:40px">
<h1>页面走丢了</h1><p class="muted">这个地址没有对应内容。可以从首页继续浏览。</p>
<p style="margin-top:24px"><a class="btn btn-primary" href="/">回到首页</a></p></div></section>"""
    write_page("404.html", "", f"页面不存在｜{SITE_NAME}", "页面不存在", four)

    # ---- sitemap / robots ----
    urls = ["", "thinking.html", "reading.html", "research.html"] + [p["out"] for p in STATIC_PAGES]
    urls += [out for item in essays for out, _ in [article_page(item)]]
    urls += [out for item in longreads for out, _ in [research_page(item)]]
    urls += [out for item in reading_notes for out, _ in [deep_note_page(item)]]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for out in urls:
        loc = f"{SITE_URL}/" if out == "" else f"{SITE_URL}/{out}"
        priority = "1.0" if out == "" else ("0.8" if out.startswith(("cases/", "research/")) else "0.7")
        lines.append(f"  <url><loc>{loc}</loc><priority>{priority}</priority></url>")
    lines.append("</urlset>")
    (PUB / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (PUB / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")

    print(f"\n构建完成 → {PUB}")
    case_count = sum(1 for p in STATIC_PAGES if p["out"].startswith("cases/"))
    print(f"页面数：首页+3 列表+{case_count} 案例+1 主题地图+{len(essays)} 思考+{len(longreads)} 研究长文+{len(reading_notes)} 读书深读")


def serve(port: int = 8777) -> None:
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(PUB), **kw)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"预览：http://127.0.0.1:{port}/  （Ctrl+C 停止）")
        httpd.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8777)
    args = ap.parse_args()
    build()
    if args.serve:
        serve(args.port)
