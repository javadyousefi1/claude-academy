#!/usr/bin/env python3
"""Build the bilingual Claude Academy handout from src/content/*.txt.

Usage:  python3 src/build.py

Content format (one file per page):

  @page                      page metadata as "key: value" lines
  @intro                     bilingual text (English, a line with ~~, then Persian)
  @section EN title | FA title
  @lesson                    metadata lines (id, en, fa, meta, url, kind), then blocks:
    #explain #analogy #example #tip #warn #try #note #steps   bilingual text blocks
    #prompt                  sample prompt: English ~~ Persian translation
    #code <lang> [caption]   raw code until a line "#end"
    #terms                   one per line: English term = Persian term = Persian definition
  @cheatsheet                bilingual bullet lists
  @quiz                      lines "Q: en || fa" and "A: en || fa"

Inline markup inside text: **bold**, ==highlight==, `code`, [label](https://url)
Lines starting with "- " form bullet lists, "1. " numbered lists, "> " a side quote.
"""
from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "src" / "content"

GROUPS = [
    ("start", "Start your journey", "شروع سفر",
     "The five on-ramps: the Claude app, Claude Code, Cowork, Claude Tag and the developer platform.",
     "پنج درِ ورود: اپ Claude، Claude Code، Cowork، Claude Tag و پلتفرم توسعه‌دهنده‌ها."),
    ("products", "Learn the products", "شناخت عمیق محصولات",
     "Go deeper: long Claude Code sessions, MCP, subagents, skills, the AI-native SDLC and enterprise rollout.",
     "یک قدم عمیق‌تر: جلسه‌های طولانی Claude Code، MCP، ساب‌ایجنت‌ها، اسکیل‌ها، چرخهٔ توسعهٔ نرم‌افزار و استقرار سازمانی."),
    ("fluency", "Become AI fluent", "سواد هوش مصنوعی",
     "How AI really works and how to work with it well: the 4D framework and its editions for every audience.",
     "هوش مصنوعی واقعاً چطور کار می‌کند و چطور خوب با آن کار کنیم: چارچوب 4D و نسخه‌هایش برای هر گروه."),
    ("api", "Build with the API", "ساختن با API",
     "From your first request to RAG, MCP and agents, on the Claude API, Amazon Bedrock and Vertex AI.",
     "از اولین درخواست تا RAG، MCP و ایجنت‌ها؛ روی Claude API، آمازون Bedrock و Vertex AI."),
    ("tutorials", "Tutorials", "آموزش‌های کوتاه",
     "Short, focused guides: one feature or one workflow at a time.",
     "راهنماهای کوتاه و متمرکز: هر بار یک قابلیت یا یک روال کاری."),
    ("usecases", "Use cases", "کاربردهای واقعی",
     "Real jobs people hand to Claude, with prompts you can copy.",
     "کارهای واقعی‌ای که آدم‌ها به Claude می‌سپارند، با پرامپت‌هایی که می‌توانی کپی کنی."),
]
GROUP_KEYS = [g[0] for g in GROUPS]
OUT_DIR = {"course": "courses", "tutorials": "tutorials", "usecases": "use-cases"}

BLOCK_LABELS = {
    "analogy": ("Think of it like this", "مثل این است که…"),
    "example": ("Real example", "مثال واقعی"),
    "tip": ("Pro tip", "نکتهٔ طلایی"),
    "warn": ("Watch out", "حواست باشد"),
    "try": ("Try it yourself", "خودت امتحان کن"),
    "note": ("Good to know", "خوب است بدانی"),
    "steps": ("Step by step", "قدم‌به‌قدم"),
    "prompt": ("Sample prompt", "پرامپت نمونه"),
    "terms": ("Key words", "واژه‌های کلیدی"),
}
TEXT_BLOCKS = {"explain", "analogy", "example", "tip", "warn", "try", "note", "steps", "prompt"}
ITEM_WORD = {"course": ("Lesson", "درس"), "tutorials": ("Tutorial", "آموزش"), "usecases": ("Use case", "کاربرد")}

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
DIRECTIVE = re.compile(r"^@(page|intro|section|lesson|cheatsheet|quiz)\b")
BLOCK_START = re.compile(r"^#(explain|analogy|example|tip|warn|try|note|steps|prompt|code|terms)\b")


def fa_num(n: int | str) -> str:
    return str(n).translate(FA_DIGITS)


def normalize_fa(text: str) -> str:
    # Arabic yeh/kaf -> Persian forms
    return text.replace("ي", "ی").replace("ك", "ک")


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- inline + block markup
INLINE_CODE = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
MARK = re.compile(r"==(.+?)==")


def inline(text: str) -> str:
    codes: list[str] = []

    def keep_code(m: re.Match) -> str:
        codes.append(m.group(1))
        return f"\u0000{len(codes) - 1}\u0000"

    text = INLINE_CODE.sub(keep_code, text)
    text = html.escape(text, quote=False)
    text = LINK.sub(lambda m: f'<a href="{html.escape(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>', text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = MARK.sub(r"<mark>\1</mark>", text)
    text = re.sub(r"\u0000(\d+)\u0000",
                  lambda m: f'<code dir="ltr">{html.escape(codes[int(m.group(1))], quote=False)}</code>', text)
    return text


def render_text(src: str) -> str:
    """Tiny markdown: paragraphs, - lists, 1. lists, > asides."""
    out: list[str] = []
    para: list[str] = []
    lst: list[str] = []
    lst_kind = ""

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst_kind
        if lst:
            out.append(f"<{lst_kind}>" + "".join(f"<li>{inline(i)}</li>" for i in lst) + f"</{lst_kind}>")
            lst.clear()
            lst_kind = ""

    for raw in src.strip("\n").split("\n"):
        line = raw.strip()
        if not line:
            flush_para()
            flush_list()
            continue
        m_ol = re.match(r"^(\d+|[۰-۹]+)[.)]\s+(.*)$", line)
        if line.startswith("- "):
            flush_para()
            if lst_kind not in ("", "ul"):
                flush_list()
            lst_kind = "ul"
            lst.append(line[2:])
        elif m_ol:
            flush_para()
            if lst_kind not in ("", "ol"):
                flush_list()
            lst_kind = "ol"
            lst.append(m_ol.group(2))
        elif line.startswith("> "):
            flush_para()
            flush_list()
            out.append('<p class="aside">' + inline(line[2:]) + "</p>")
        elif lst and raw.startswith("  "):
            lst[-1] += " " + line  # continuation of a list item
        else:
            flush_list()
            para.append(line)
    flush_para()
    flush_list()
    return "\n".join(out)


def split_bi(body: str, where: str) -> tuple[str, str]:
    parts = re.split(r"^~~\s*$", body, flags=re.M)
    if len(parts) != 2:
        raise BuildError(f"{where}: expected English and Persian parts separated by a '~~' line")
    return parts[0].strip("\n"), normalize_fa(parts[1].strip("\n"))


def pair(en_html: str, fa_html: str, extra: str = "") -> str:
    return (f'<div class="pair{extra}">'
            f'<div class="en" lang="en" dir="ltr">{en_html}</div>'
            f'<div class="fa" lang="fa" dir="rtl">{fa_html}</div></div>')


# ---------------------------------------------------------------- data model
@dataclass
class Block:
    kind: str
    body: str
    arg: str = ""


@dataclass
class Item:
    meta: dict
    blocks: list[Block] = field(default_factory=list)
    section: tuple[str, str] | None = None


@dataclass
class Page:
    path: Path
    meta: dict
    intro: str = ""
    items: list[Item] = field(default_factory=list)
    sections: list[tuple[str, str]] = field(default_factory=list)
    cheatsheet: str = ""
    quiz: list[tuple[str, str, str, str]] = field(default_factory=list)
    extra_blocks: list[Block] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.meta.get("kind", "course")

    @property
    def slug(self) -> str:
        return self.meta["slug"]

    @property
    def out_rel(self) -> str:
        return f"{OUT_DIR[self.kind]}/{self.slug}.html"


def parse_meta_lines(lines: list[str], where: str) -> dict:
    meta = {}
    for ln in lines:
        if not ln.strip():
            continue
        if ":" not in ln:
            raise BuildError(f"{where}: bad metadata line {ln!r}")
        k, v = ln.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        meta[k.strip()] = normalize_fa(v)
    return meta


def parse_file(path: Path) -> Page:
    lines = path.read_text(encoding="utf-8").split("\n")
    page: Page | None = None
    cur_top = None          # 'page' | 'intro' | 'lesson' | 'cheatsheet' | 'quiz' | 'section'
    cur_item: Item | None = None
    cur_block: Block | None = None
    meta_buf: list[str] = []
    text_buf: list[str] = []
    cur_section = None
    i = 0
    where = path.name

    def close_block():
        nonlocal cur_block
        if cur_block is not None:
            cur_block.body = "\n".join(text_buf).strip("\n")
            target = cur_item.blocks if cur_item is not None else page.extra_blocks
            target.append(cur_block)
            cur_block = None
            text_buf.clear()

    def close_top():
        nonlocal cur_top, cur_item, page
        if cur_top == "page":
            page = Page(path=path, meta=parse_meta_lines(meta_buf, where))
        elif cur_top == "lesson":
            close_block()
            if cur_item is not None and not cur_item.meta:
                cur_item.meta = parse_meta_lines(meta_buf, where)
            page.items.append(cur_item)
            cur_item = None
        elif cur_top == "intro":
            page.intro = "\n".join(text_buf).strip("\n")
            text_buf.clear()
        elif cur_top == "cheatsheet":
            page.cheatsheet = "\n".join(text_buf).strip("\n")
            text_buf.clear()
        elif cur_top == "quiz":
            q = None
            for ln in text_buf:
                ln = ln.strip()
                if ln.startswith("Q:"):
                    q = ln[2:].split("||")
                elif ln.startswith("A:"):
                    a = ln[2:].split("||")
                    if q is None or len(q) != 2 or len(a) != 2:
                        raise BuildError(f"{where}: quiz lines need 'Q: en || fa' then 'A: en || fa'")
                    page.quiz.append((q[0].strip(), normalize_fa(q[1].strip()), a[0].strip(), normalize_fa(a[1].strip())))
                    q = None
            text_buf.clear()
        meta_buf.clear()
        cur_top = None

    while i < len(lines):
        line = lines[i]
        if DIRECTIVE.match(line):
            close_top()
            head = line[1:].strip()
            word, _, rest = head.partition(" ")
            if word == "page":
                cur_top = "page"
            elif word == "intro":
                cur_top = "intro"
            elif word == "section":
                en, _, fa = rest.partition("|")
                cur_section = (en.strip(), normalize_fa(fa.strip()))
                page.sections.append(cur_section)
                cur_top = None
            elif word == "lesson":
                cur_top = "lesson"
                cur_item = Item(meta={}, section=cur_section)
            elif word == "cheatsheet":
                cur_top = "cheatsheet"
            elif word == "quiz":
                cur_top = "quiz"
            else:
                raise BuildError(f"{where}:{i + 1}: unknown directive @{word}")
            i += 1
            continue
        if cur_top == "lesson" and BLOCK_START.match(line):
            if cur_item is not None and not cur_item.meta:
                cur_item.meta = parse_meta_lines(meta_buf, where)
                meta_buf.clear()
            close_block()
            head = line[1:].strip()
            kind, _, arg = head.partition(" ")
            if kind not in TEXT_BLOCKS | {"code", "terms"}:
                raise BuildError(f"{where}:{i + 1}: unknown block #{kind}")
            cur_block = Block(kind=kind, body="", arg=arg.strip())
            i += 1
            if kind == "code":
                while i < len(lines) and lines[i].rstrip() != "#end":
                    text_buf.append(lines[i])
                    i += 1
                if i >= len(lines):
                    raise BuildError(f"{where}: #code block without #end")
                i += 1  # skip #end
                close_block()
            continue
        if cur_top == "page" or (cur_top == "lesson" and cur_block is None):
            meta_buf.append(line)
        elif cur_top in ("intro", "cheatsheet", "quiz") or cur_block is not None:
            text_buf.append(line)
        elif line.strip():
            raise BuildError(f"{where}:{i + 1}: text outside of a block: {line[:60]!r}")
        i += 1
    close_top()
    if page is None:
        raise BuildError(f"{where}: missing @page")
    for key in ("slug", "en", "fa", "group"):
        if key not in page.meta:
            raise BuildError(f"{where}: @page needs '{key}'")
    if page.meta["group"] not in GROUP_KEYS:
        raise BuildError(f"{where}: unknown group {page.meta['group']}")
    seen = set()
    for it in page.items:
        for key in ("id", "en", "fa"):
            if key not in it.meta:
                raise BuildError(f"{where}: lesson missing '{key}' ({it.meta})")
        if it.meta["id"] in seen:
            raise BuildError(f"{where}: duplicate lesson id {it.meta['id']}")
        seen.add(it.meta["id"])
        if not any(b.kind == "explain" for b in it.blocks):
            raise BuildError(f"{where}: lesson {it.meta['id']} has no #explain block")
    expect = page.meta.get("expect")
    if expect and int(expect) != len(page.items):
        raise BuildError(f"{where}: expected {expect} items, found {len(page.items)}")
    return page


# ---------------------------------------------------------------- rendering
FONT_LINK = ("https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400"
             "&family=JetBrains+Mono:wght@400;600&family=Lalezar&family=Vazirmatn:wght@400;500;700;800&display=swap")
HLJS = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"


def head(title: str, rel: str, has_code: bool, description: str) -> str:
    code_js = f'\n<script src="{HLJS}" defer></script>' if has_code else ""
    return f"""<!doctype html>
<html lang="fa" dir="rtl" data-lang="both">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONT_LINK}">
<link rel="stylesheet" href="{rel}assets/style.css">
<script>try{{var l=localStorage.getItem("ca-lang");if(l)document.documentElement.setAttribute("data-lang",l)}}catch(e){{}}</script>{code_js}
<script src="{rel}assets/app.js" defer></script>
</head>
<body>
<a class="skip" href="#main">پرش به متن اصلی</a>
"""


def topbar(rel: str, crumbs: list[tuple[str, str]]) -> str:
    crumb_html = "".join(
        f'<span class="crumb-sep" aria-hidden="true">/</span><a href="{href}">{html.escape(label)}</a>' if href else
        f'<span class="crumb-sep" aria-hidden="true">/</span><span>{html.escape(label)}</span>'
        for label, href in crumbs)
    return f"""<header class="topbar">
  <nav class="crumbs" aria-label="مسیر صفحه"><a class="brand" href="{rel}index.html"><span class="brand-mark" aria-hidden="true">C</span><span>جزوهٔ Claude Academy</span></a>{crumb_html}</nav>
  <div class="lang-switch" role="group" aria-label="زبان نمایش">
    <button type="button" data-set-lang="both" aria-pressed="true">دوزبانه</button>
    <button type="button" data-set-lang="fa" aria-pressed="false">فارسی</button>
    <button type="button" data-set-lang="en" aria-pressed="false" lang="en">English</button>
  </div>
</header>
"""


def footer(rel: str) -> str:
    return f"""<footer class="site-foot">
  <p>این جزوه یک بازنویسی آموزشی و آزاد از مطالب <a href="https://academy.claude.com" target="_blank" rel="noopener">Claude Academy</a> است؛ متن‌ها، تشبیه‌ها و مثال‌ها تازه نوشته شده‌اند. برای جدیدترین نسخه همیشه به صفحهٔ رسمی هر درس سر بزن.</p>
  <p lang="en" dir="ltr">An independent study companion to Claude Academy. Explanations and examples are original; follow each "official page" link for the source lesson.</p>
  <p><a href="{rel}index.html">بازگشت به فهرست کامل</a> · <a href="{rel}glossary.html">واژه‌نامه</a></p>
</footer>
"""


def render_block(b: Block, where: str) -> str:
    if b.kind == "code":
        lang, _, caption = b.arg.partition(" ")
        lang = lang or "text"
        cap = html.escape(caption.strip()) if caption.strip() else ""
        cap_html = f'<span class="code-cap">{cap}</span>' if cap else ""
        return (f'<figure class="code" dir="ltr"><figcaption><span class="code-lang">{html.escape(lang)}</span>{cap_html}'
                f'<button type="button" class="copy" data-copy-target="code">کپی</button></figcaption>'
                f'<pre><code class="language-{html.escape(lang)}">{html.escape(b.body)}</code></pre></figure>')
    if b.kind == "terms":
        rows = []
        for ln in b.body.split("\n"):
            if not ln.strip():
                continue
            parts = [p.strip() for p in ln.split("=")]
            if len(parts) != 3:
                raise BuildError(f"{where}: #terms line needs 'en = fa = definition': {ln!r}")
            rows.append(f'<div class="term"><dt><span lang="en" dir="ltr">{html.escape(parts[0])}</span>'
                        f'<span class="term-fa">{html.escape(normalize_fa(parts[1]))}</span></dt>'
                        f'<dd>{inline(normalize_fa(parts[2]))}</dd></div>')
        en, fa = BLOCK_LABELS["terms"]
        return (f'<section class="blk blk-terms"><h4 class="blk-label"><span lang="en">{en}</span>'
                f'<span>{fa}</span></h4><dl class="terms">{"".join(rows)}</dl></section>')
    en_src, fa_src = split_bi(b.body, f"{where} #{b.kind}")
    if b.kind == "explain":
        return f'<section class="blk blk-explain">{pair(render_text(en_src), render_text(fa_src))}</section>'
    en_label, fa_label = BLOCK_LABELS[b.kind]
    if b.kind == "prompt":
        body = pair(f'<div class="prompt-text">{render_text(en_src)}</div>'
                    f'<button type="button" class="copy" data-copy-target=".prompt-text">Copy</button>',
                    f'<div class="prompt-text">{render_text(fa_src)}</div>'
                    f'<button type="button" class="copy" data-copy-target=".prompt-text">کپی</button>', " pair-prompt")
    else:
        body = pair(render_text(en_src), render_text(fa_src))
    return (f'<section class="blk blk-{b.kind}"><h4 class="blk-label"><span lang="en">{en_label}</span>'
            f'<span>{fa_label}</span></h4>{body}</section>')


def anchor(page: Page, item: Item) -> str:
    return f"{page.slug}--{item.meta['id']}"


def render_item(page: Page, item: Item, n: int) -> str:
    where = f"{page.path.name}:{item.meta['id']}"
    m = item.meta
    word_en, word_fa = ITEM_WORD[page.kind]
    kind = m.get("kind", "")
    badge = ""
    if kind:
        badge_map = {"quiz": ("Quiz", "آزمون"), "exercise": ("Exercise", "تمرین"), "video": ("Video", "ویدیو"),
                     "project": ("Project", "پروژه"), "wrap": ("Wrap-up", "جمع‌بندی"), "brief": ("Same as API course", "مشترک با دورهٔ API")}
        b_en, b_fa = badge_map.get(kind, (kind, kind))
        badge = f'<span class="badge badge-{html.escape(kind)}"><span lang="en">{b_en}</span> · {b_fa}</span>'
    meta_bits = f'<span class="item-meta">{html.escape(m["meta"])}</span>' if m.get("meta") else ""
    src = (f'<a class="src" href="{html.escape(m["url"])}" target="_blank" rel="noopener">صفحهٔ رسمی<span aria-hidden="true"> ↗</span></a>'
           if m.get("url") else "")
    cid = anchor(page, item)
    blocks = "\n".join(render_block(b, where) for b in item.blocks)
    return f"""<article class="item" id="{cid}" data-item="{cid}">
  <header class="item-head">
    <div class="item-num" aria-hidden="true">{fa_num(n)}</div>
    <div class="item-titles">
      <p class="item-kicker">{word_fa} {fa_num(n)} <span lang="en" dir="ltr">· {word_en} {n}</span> {badge}</p>
      <h3><span class="t-fa">{inline(m['fa'])}</span><span class="t-en" lang="en" dir="ltr">{inline(m['en'])}</span></h3>
      <div class="item-tools">{meta_bits}{src}<label class="done"><input type="checkbox" id="done-{cid}" data-done="{cid}"> خواندم</label></div>
    </div>
  </header>
  <div class="item-body">
{blocks}
  </div>
</article>"""


def render_page(page: Page, pages_in_order: list[Page], glossary: list) -> str:
    rel = "../"
    group = next(g for g in GROUPS if g[0] == page.meta["group"])
    title = f"{page.meta['fa']} | {page.meta['en']}"
    has_code = any(b.kind == "code" for it in page.items for b in it.blocks)
    desc = page.meta.get("desc_en", page.meta["en"])
    out = [head(title, rel, has_code, desc), topbar(rel, [(group[2], f"{rel}index.html#{group[0]}"), (page.meta["fa"], "")])]

    # side table of contents
    toc = ['<nav class="side-toc" aria-label="فهرست این صفحه"><details open><summary>فهرست این صفحه '
           f'<span class="toc-count">{fa_num(len(page.items))} مورد</span></summary><ol>']
    last_section = None
    for n, it in enumerate(page.items, 1):
        if it.section and it.section != last_section:
            toc.append(f'<li class="toc-sec">{html.escape(it.section[1])}</li>')
            last_section = it.section
        toc.append(f'<li><a href="#{anchor(page, it)}" data-toc="{anchor(page, it)}"><span class="toc-n">{fa_num(n)}</span>'
                   f'<span class="toc-t">{inline(it.meta["fa"])}</span></a></li>')
    extra_links = []
    if page.cheatsheet:
        extra_links.append('<li><a href="#cheatsheet"><span class="toc-n">★</span><span class="toc-t">خلاصهٔ یک‌نگاه</span></a></li>')
    if page.quiz:
        extra_links.append('<li><a href="#selfcheck"><span class="toc-n">؟</span><span class="toc-t">خودت را بسنج</span></a></li>')
    toc.extend(extra_links)
    toc.append("</ol></details></nav>")

    stats = page.meta.get("stats", "")
    who_en, who_fa = page.meta.get("who_en", ""), page.meta.get("who_fa", "")
    src = (f'<a class="src src-big" href="{html.escape(page.meta["url"])}" target="_blank" rel="noopener">'
           f'صفحهٔ رسمی در Claude Academy<span aria-hidden="true"> ↗</span></a>' if page.meta.get("url") else "")
    intro_html = ""
    if page.intro:
        en, fa = split_bi(page.intro, f"{page.path.name} @intro")
        intro_html = f'<div class="page-intro">{pair(render_text(en), render_text(fa))}</div>'
    who_html = ""
    if who_en or who_fa:
        who_html = (f'<p class="who"><span class="who-label">مناسب برای</span> <span>{inline(who_fa)}</span>'
                    f' <span class="who-en" lang="en" dir="ltr">{inline(who_en)}</span></p>')
    progress = (f'<p class="progress" data-progress-for="{page.slug}" data-total="{len(page.items)}">'
                f'<span class="progress-bar"><span></span></span><span class="progress-text">'
                f'۰ از {fa_num(len(page.items))} خوانده شده</span></p>')
    out.append(f"""<div class="layout">
{"".join(toc)}
<main id="main">
<header class="page-head">
  <p class="eyebrow">{html.escape(group[2])} <span lang="en" dir="ltr">· {html.escape(group[1])}</span></p>
  <h1><span class="h1-fa">{inline(page.meta['fa'])}</span><span class="h1-en" lang="en" dir="ltr">{inline(page.meta['en'])}</span></h1>
  <p class="page-stats"><span lang="en" dir="ltr">{html.escape(stats)}</span> {src}</p>
  {who_html}
  {progress}
</header>
{intro_html}
""")
    last_section = None
    for n, it in enumerate(page.items, 1):
        if it.section and it.section != last_section:
            out.append(f'<h2 class="section-title"><span>{html.escape(it.section[1])}</span>'
                       f'<span class="sec-en" lang="en" dir="ltr">{html.escape(it.section[0])}</span></h2>')
            last_section = it.section
        out.append(render_item(page, it, n))

    if page.cheatsheet:
        en, fa = split_bi(page.cheatsheet, f"{page.path.name} @cheatsheet")
        out.append(f'<section class="cheatsheet" id="cheatsheet"><h2 class="section-title"><span>خلاصهٔ یک‌نگاه</span>'
                   f'<span class="sec-en" lang="en" dir="ltr">Cheat sheet</span></h2>{pair(render_text(en), render_text(fa))}</section>')
    if page.quiz:
        qs = []
        for k, (qen, qfa, aen, afa) in enumerate(page.quiz, 1):
            qs.append(f'<details class="q"><summary><span class="q-n">{fa_num(k)}</span>'
                      f'{pair(inline(qen), inline(qfa), " pair-q")}</summary>'
                      f'<div class="a">{pair(inline(aen), inline(afa))}</div></details>')
        out.append(f'<section class="selfcheck" id="selfcheck"><h2 class="section-title"><span>خودت را بسنج</span>'
                   f'<span class="sec-en" lang="en" dir="ltr">Check yourself</span></h2>'
                   f'<p class="hint">اول جواب را در ذهنت بگو، بعد روی سؤال بزن تا پاسخ باز شود.</p>{"".join(qs)}</section>')

    # prev / next
    idx = pages_in_order.index(page)
    nav = ['<nav class="pager" aria-label="صفحهٔ قبلی و بعدی">']
    if idx > 0:
        p = pages_in_order[idx - 1]
        nav.append(f'<a class="prev" href="{rel}{p.out_rel}"><span class="pager-label">قبلی</span>'
                   f'<span>{html.escape(p.meta["fa"])}</span></a>')
    else:
        nav.append("<span></span>")
    if idx < len(pages_in_order) - 1:
        p = pages_in_order[idx + 1]
        nav.append(f'<a class="next" href="{rel}{p.out_rel}"><span class="pager-label">بعدی</span>'
                   f'<span>{html.escape(p.meta["fa"])}</span></a>')
    nav.append("</nav>")
    out.append("".join(nav))
    out.append("</main>\n</div>\n")
    out.append(footer(rel))
    out.append("</body>\n</html>\n")
    return "\n".join(out)


def collect_terms(pages: list[Page]) -> list[tuple[str, str, str, str, str]]:
    terms = {}
    for p in pages:
        for it in p.items:
            for b in it.blocks:
                if b.kind != "terms":
                    continue
                for ln in b.body.split("\n"):
                    if not ln.strip():
                        continue
                    en, fa, d = [x.strip() for x in ln.split("=")]
                    key = en.lower()
                    if key not in terms:
                        terms[key] = (en, normalize_fa(fa), normalize_fa(d), f"{p.out_rel}#{anchor(p, it)}", p.meta["fa"])
    return sorted(terms.values(), key=lambda t: t[0].lower())


def render_glossary(terms, pages_count: int) -> str:
    rel = ""
    out = [head("واژه‌نامه | Claude Academy Glossary", rel, False, "English-Persian glossary of Claude terms"),
           topbar(rel, [("واژه‌نامه", "")])]
    rows = []
    for en, fa, d, href, where in terms:
        rows.append(f'<div class="term" data-search="{html.escape((en + " " + fa + " " + d).lower())}"><dt>'
                    f'<span lang="en" dir="ltr">{html.escape(en)}</span><span class="term-fa">{html.escape(fa)}</span></dt>'
                    f'<dd>{inline(d)} <a class="term-src" href="{href}">در «{html.escape(where)}»</a></dd></div>')
    out.append(f"""<main id="main" class="solo">
<header class="page-head">
  <p class="eyebrow">مرجع سریع <span lang="en" dir="ltr">· Quick reference</span></p>
  <h1><span class="h1-fa">واژه‌نامهٔ انگلیسی–فارسی</span><span class="h1-en" lang="en" dir="ltr">English–Persian glossary</span></h1>
  <p class="page-stats">{fa_num(len(terms))} واژه، جمع‌شده از همهٔ درس‌ها. کنار هر واژه لینک درسی است که آن را توضیح داده.</p>
</header>
<div class="search-box"><label for="q-glossary">جست‌وجو در واژه‌ها</label><input id="q-glossary" type="search" placeholder="مثلاً: token یا پنجرهٔ زمینه" data-filter=".terms .term" autocomplete="off"></div>
<dl class="terms terms-full">{"".join(rows)}</dl>
</main>
""")
    out.append(footer(rel))
    out.append("</body>\n</html>\n")
    return "\n".join(out)


def render_index(pages: list[Page], terms_count: int, index_extra: str) -> str:
    rel = ""
    total_items = sum(len(p.items) for p in pages)
    by_group = {g[0]: [p for p in pages if p.meta["group"] == g[0]] for g in GROUPS}
    out = [head("جزوهٔ Claude Academy", rel, False,
                "Every Claude Academy course, tutorial and use case explained simply in English and Persian."),
           topbar(rel, [])]
    counts = {
        "courses": sum(1 for p in pages if p.kind == "course"),
        "lessons": sum(len(p.items) for p in pages if p.kind == "course"),
        "tutorials": sum(len(p.items) for p in pages if p.kind == "tutorials"),
        "usecases": sum(len(p.items) for p in pages if p.kind == "usecases"),
    }
    out.append(f"""<main id="main" class="solo home">
<header class="hero">
  <p class="eyebrow">جزوهٔ دوزبانه <span lang="en" dir="ltr">· A bilingual study handbook</span></p>
  <h1><span class="h1-fa">جزوهٔ کامل Claude Academy</span><span class="h1-en" lang="en" dir="ltr">Claude Academy, explained like you're ten</span></h1>
  <p class="lede">همهٔ دوره‌ها، آموزش‌ها و کاربردهای سایت رسمی Claude Academy، درس‌به‌درس؛ هر درس اول به انگلیسی ساده و بعد با ترجمهٔ روان فارسی، همراه با تشبیه، مثال واقعی و نکته‌های طلایی.</p>
  <p class="lede-en" lang="en" dir="ltr">Every course, tutorial and use case from the official Claude Academy, lesson by lesson: plain English first, a fluent Persian translation beside it, plus analogies, real examples and pro tips.</p>
  <p class="totals"><span><b>{fa_num(counts['courses'])}</b> دوره</span><span><b>{fa_num(counts['lessons'])}</b> درس</span><span><b>{fa_num(counts['tutorials'])}</b> آموزش کوتاه</span><span><b>{fa_num(counts['usecases'])}</b> کاربرد واقعی</span><span><b>{fa_num(terms_count)}</b> واژه در <a href="glossary.html">واژه‌نامه</a></span></p>
</header>
{index_extra}
<div class="search-box"><label for="q-index">دنبال چه می‌گردی؟</label><input id="q-index" type="search" placeholder="مثلاً: MCP، پرامپت، اکسل، skills…" data-filter=".catalog .card" autocomplete="off"></div>
<div class="catalog">
""")
    for key, gen, gfa, gden, gdfa in GROUPS:
        plist = by_group[key]
        if not plist:
            continue
        cards = []
        for p in plist:
            n_items = len(p.items)
            unit = {"course": "درس", "tutorials": "آموزش", "usecases": "کاربرد"}[p.kind]
            search = " ".join([p.meta["en"], p.meta["fa"]] + [it.meta["en"] + " " + it.meta["fa"] for it in p.items]).lower()
            cards.append(f"""<a class="card" href="{p.out_rel}" data-search="{html.escape(search)}" data-progress-for="{p.slug}" data-total="{n_items}">
  <span class="card-title"><span class="card-fa">{inline(p.meta['fa'])}</span><span class="card-en" lang="en" dir="ltr">{inline(p.meta['en'])}</span></span>
  <span class="card-blurb">{inline(p.meta.get('blurb_fa', ''))}</span>
  <span class="card-foot"><span>{fa_num(n_items)} {unit}</span><span lang="en" dir="ltr">{html.escape(p.meta.get('stats', ''))}</span><span class="card-progress" aria-label="پیشرفت"><span></span></span></span>
</a>""")
        out.append(f"""<section class="group" id="{key}">
  <h2 class="group-title"><span>{gfa}</span><span class="sec-en" lang="en" dir="ltr">{gen}</span></h2>
  {pair(inline(gden), inline(gdfa), " pair-group")}
  <div class="cards">{''.join(cards)}</div>
</section>""")
    out.append("</div>\n</main>\n")
    out.append(footer(rel))
    out.append("</body>\n</html>\n")
    return "\n".join(out)


def main() -> int:
    files = sorted(CONTENT.glob("*.txt"))
    if not files:
        print("no content files", file=sys.stderr)
        return 1
    try:
        pages = [parse_file(f) for f in files]
    except BuildError as e:
        print(f"BUILD ERROR: {e}", file=sys.stderr)
        return 1
    pages.sort(key=lambda p: (GROUP_KEYS.index(p.meta["group"]), float(p.meta.get("order", 99)), p.slug))
    slugs = [p.slug for p in pages]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        print(f"BUILD ERROR: duplicate page slugs {dupes}", file=sys.stderr)
        return 1
    terms = collect_terms(pages)
    try:
        for p in pages:
            out = ROOT / p.out_rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_page(p, pages, terms), encoding="utf-8")
    except BuildError as e:
        print(f"BUILD ERROR: {e}", file=sys.stderr)
        return 1
    extra_path = CONTENT.parent / "index-extra.html"
    extra = extra_path.read_text(encoding="utf-8") if extra_path.exists() else ""
    (ROOT / "index.html").write_text(render_index(pages, len(terms), extra), encoding="utf-8")
    (ROOT / "glossary.html").write_text(render_glossary(terms, len(pages)), encoding="utf-8")
    manifest = [{"slug": p.slug, "kind": p.kind, "group": p.meta["group"], "en": p.meta["en"], "fa": p.meta["fa"],
                 "items": [it.meta["id"] for it in p.items]} for p in pages]
    (ROOT / "src" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(p.items) for p in pages)
    print(f"built {len(pages)} pages, {total} items, {len(terms)} glossary terms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
