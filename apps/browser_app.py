"""
Browser -- a minimal text-only browser, but with the interaction model of
a real one: a persistent omnibox (address bar) with Back/Forward/Reload
and a bookmark star, real per-tab navigation history (Back/Forward move
through *previously fetched* pages instantly, no re-fetch), tappable
in-page links, and a New Tab page showing bookmark shortcuts as tiles
(Chrome's "most visited" grid) instead of a plain list.

It still can't run JS or lay out CSS -- this is a phone-OS-scale browser
that fetches a page and flows its text -- but the navigation *feels*
like a browser now instead of a text reader with a URL box bolted on.
"""

import os
import re
import json
import textwrap
from urllib.parse import urljoin
from html.parser import HTMLParser
from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT, FG_COLOR

DEFAULT_BOOKMARKS = [
    {"title": "Example.com", "url": "https://example.com"},
    {"title": "Anthropic", "url": "https://www.anthropic.com"},
    {"title": "Wikipedia (random)", "url": "https://en.wikipedia.org/wiki/Special:Random"},
    {"title": "Hacker News", "url": "https://news.ycombinator.com"},
]

BOOKMARKS_PATH = os.path.expanduser("~/.kos_bookmarks.json")

LINES_PER_PAGE = 13
CHARS_PER_LINE = 38
KEYBOARD_H = 188
MAX_URL_LEN = 60
MAX_TITLE_LEN = 24

TAB_BAR_H = 30
OMNIBOX_H = 38
MAX_TABS = 4
CONTENT_TOP = STATUS_BAR_H + TAB_BAR_H + OMNIBOX_H
LINK_COLOR = (90, 160, 240)


def load_bookmarks():
    try:
        with open(BOOKMARKS_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            return [b for b in data if "title" in b and "url" in b]
    except Exception:
        pass
    return [dict(b) for b in DEFAULT_BOOKMARKS]


def save_bookmarks(bookmarks):
    try:
        with open(BOOKMARKS_PATH, "w") as f:
            json.dump(bookmarks, f)
    except Exception:
        pass


class _TextExtractor(HTMLParser):
    """HTML-to-text, but keeps track of <a href> spans (for tappable
    links) and the <title> (for a real tab label) along the way."""

    BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.chunks = []  # list of (text, url_or_None)
        self.title = ""
        self._skip = False
        self._in_title = False
        self._link_stack = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._link_stack.append(dict(attrs).get("href"))
        elif tag in self.BLOCK_TAGS:
            self.chunks.append(("\n", None))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._link_stack:
            self._link_stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + data).strip()
            return
        if self._skip:
            return
        text = data.strip()
        if text:
            url = self._link_stack[-1] if self._link_stack else None
            self.chunks.append((text, url))


def _wrap_runs(chunks, width_chars):
    """Greedy word-wrap that keeps each word tagged with its link URL
    (or None), so the renderer can color/tap links word-by-word."""
    lines, current, current_len = [], [], 0
    for text, url in chunks:
        if text == "\n":
            if current:
                lines.append(current)
                current, current_len = [], 0
            continue
        for word in text.split():
            add_len = len(word) + (1 if current else 0)
            if current and current_len + add_len > width_chars:
                lines.append(current)
                current, current_len = [], 0
            current.append((word, url))
            current_len += len(word) + (1 if current_len else 0)
    if current:
        lines.append(current)
    return lines


def _new_tab():
    return {"history": [], "hist_index": -1, "page_index": 0}


class BrowserApp(App):
    name = "Browser"
    icon = "\U0001F310"

    def on_open(self):
        self.bookmarks = load_bookmarks()
        self.tabs = [_new_tab()]
        self.active = 0
        self.mode = "browse"      # browse | type | bm_edit
        self.editing_bookmarks = False
        self.status = None
        self.keyboard = None
        self.draft_url = ""
        self.bm_edit = None
        self._link_hits = []
        self._rebuild()

    # -- tab / history helpers ------------------------------------------------
    @property
    def tab(self):
        return self.tabs[self.active]

    def _cur_entry(self, tab=None):
        tab = tab or self.tab
        return tab["history"][tab["hist_index"]] if tab["hist_index"] >= 0 else None

    def _select_tab(self, i):
        self.active = i
        self.mode = "browse"
        self._rebuild()

    def _close_tab(self, i):
        del self.tabs[i]
        if not self.tabs:
            self.tabs = [_new_tab()]
            self.active = 0
        else:
            self.active = min(i, len(self.tabs) - 1)
        self.mode = "browse"
        self._rebuild()

    def _add_tab(self):
        if len(self.tabs) >= MAX_TABS:
            self.status = "Tab limit reached"
            return
        self.tabs.append(_new_tab())
        self.active = len(self.tabs) - 1
        self.mode = "browse"
        self._rebuild()

    # -- building all buttons (tab strip + omnibox + content) ---------------
    def _rebuild(self):
        self.buttons = []
        self._build_tab_strip()
        if self.mode == "type":
            self._build_type_buttons()
        elif self.mode == "bm_edit":
            self._build_bm_edit_buttons()
        else:
            self._build_omnibox_buttons()
            entry = self._cur_entry()
            if entry:
                self._build_page_buttons()
            else:
                self._build_newtab_buttons()

    def _build_tab_strip(self):
        n = len(self.tabs)
        plus_w = 30
        tab_w = (SCREEN_W - plus_w) // n
        for i in range(n):
            x = i * tab_w
            if n > 1:
                self.buttons.append(
                    Button(x + tab_w - 22, STATUS_BAR_H, 22, TAB_BAR_H, "\u2715",
                           (lambda i=i: self._close_tab(i)), font=FONT_SM))
            self.buttons.append(
                Button(x, STATUS_BAR_H, tab_w, TAB_BAR_H, "",
                       (lambda i=i: self._select_tab(i)), font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W - plus_w, STATUS_BAR_H, plus_w, TAB_BAR_H, "+",
                   self._add_tab, font=FONT_MD))

    # -- omnibox: back / forward / url / star / reload -----------------------
    def _build_omnibox_buttons(self):
        y = STATUS_BAR_H + TAB_BAR_H
        self.buttons.append(Button(2, y, 34, OMNIBOX_H, "\u2190", self._go_back, font=FONT_MD))
        self.buttons.append(Button(38, y, 34, OMNIBOX_H, "\u2192", self._go_forward, font=FONT_MD))
        self.buttons.append(Button(74, y, SCREEN_W - 74 - 76, OMNIBOX_H, "",
                                    self._start_typing, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 76, y, 38, OMNIBOX_H, "\u2606",
                                    self._toggle_bookmark_current, font=FONT_MD))
        self.buttons.append(Button(SCREEN_W - 38, y, 36, OMNIBOX_H, "\u27F3",
                                    self._reload, font=FONT_MD))

    def _go_back(self):
        tab = self.tab
        if tab["hist_index"] > 0:
            tab["hist_index"] -= 1
            tab["page_index"] = 0
            self.mode = "browse"
            self._rebuild()

    def _go_forward(self):
        tab = self.tab
        if tab["hist_index"] < len(tab["history"]) - 1:
            tab["hist_index"] += 1
            tab["page_index"] = 0
            self.mode = "browse"
            self._rebuild()

    def _reload(self):
        entry = self._cur_entry()
        if not entry:
            return
        try:
            pages, title = self._fetch_and_wrap(entry["url"])
        except Exception as e:
            self.status = f"Couldn't reload: {e}"
            self._rebuild()
            return
        entry["pages"] = pages
        if title:
            entry["title"] = title
        self.tab["page_index"] = 0
        self._rebuild()

    def _toggle_bookmark_current(self):
        entry = self._cur_entry()
        if not entry:
            return
        if any(b["url"] == entry["url"] for b in self.bookmarks):
            self.bookmarks = [b for b in self.bookmarks if b["url"] != entry["url"]]
            self.status = "Removed bookmark"
        else:
            self.bookmarks.append({"title": entry["title"], "url": entry["url"]})
            self.status = "Bookmarked"
        save_bookmarks(self.bookmarks)

    # -- new tab: bookmark tiles (Chrome-style shortcuts) --------------------
    def _build_newtab_buttons(self):
        top = CONTENT_TOP + 8
        self.buttons.append(
            Button(SCREEN_W - 74, top, 60, 30,
                   "Done" if self.editing_bookmarks else "Edit",
                   self._toggle_edit_bookmarks, font=FONT_SM))

        tile_top = top + 40
        cols = 3
        margin = 14
        cell = (SCREEN_W - margin * (cols + 1)) // cols
        items = list(self.bookmarks)
        for i, b in enumerate(items):
            r, c = divmod(i, cols)
            x = margin + c * (cell + margin)
            y = tile_top + r * (cell + margin)
            if y > SCREEN_H - 130:
                break
            self.buttons.append(
                Button(x, y, cell, cell, "", self._open_bookmark(b), font=FONT_SM))
            if self.editing_bookmarks:
                self.buttons.append(
                    Button(x + cell - 26, y, 26, 26, "\u270E",
                           (lambda i=i: self._start_edit_bookmark(i)), font=FONT_SM))

        if self.editing_bookmarks:
            n = len(items)
            r, c = divmod(n, cols)
            x = margin + c * (cell + margin)
            y = tile_top + r * (cell + margin)
            if y <= SCREEN_H - 130:
                self.buttons.append(Button(x, y, cell, cell, "+", self._start_add_bookmark, font=FONT_LG))

    def _toggle_edit_bookmarks(self):
        self.editing_bookmarks = not self.editing_bookmarks
        self._rebuild()

    def _open_bookmark(self, b):
        def handler():
            self._navigate(b["title"], b["url"])
        return handler

    # -- typing a URL in the omnibox -----------------------------------------
    def _start_typing(self):
        self.mode = "type"
        entry = self._cur_entry()
        self.draft_url = entry["url"] if entry else "https://"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _build_type_buttons(self):
        y = STATUS_BAR_H + TAB_BAR_H + 8
        self.buttons.append(Button(16, y + 84, 90, 34, "Cancel", self._cancel_typing, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 106, y + 84, 90, 34, "Go", self._go_to_draft, font=FONT_SM))

    def _cancel_typing(self):
        self.mode = "browse"
        self._rebuild()

    def _go_to_draft(self):
        url = self.draft_url.strip()
        if url and url != "https://":
            self._navigate(url, url)
        else:
            self.mode = "browse"
            self._rebuild()

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft_url = self.draft_url[:-1]
        elif val == "ENTER":
            self._go_to_draft()
        elif len(self.draft_url) < MAX_URL_LEN:
            self.draft_url += val

    # -- add/edit bookmarks ---------------------------------------------------
    def _start_add_bookmark(self):
        self.bm_edit = {"idx": None, "field": "title", "title": "", "url": "https://"}
        self.mode = "bm_edit"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _start_edit_bookmark(self, idx):
        b = self.bookmarks[idx]
        self.bm_edit = {"idx": idx, "field": "title", "title": b["title"], "url": b["url"]}
        self.mode = "bm_edit"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _build_bm_edit_buttons(self):
        y0 = STATUS_BAR_H + TAB_BAR_H + 8
        self.buttons.append(
            Button(16, y0 + 30, SCREEN_W - 32, 34, "", self._focus_field("title"),
                   bg=(46, 46, 56) if self.bm_edit["field"] == "title" else CARD_COLOR, font=FONT_SM))
        self.buttons.append(
            Button(16, y0 + 72, SCREEN_W - 32, 34, "", self._focus_field("url"),
                   bg=(46, 46, 56) if self.bm_edit["field"] == "url" else CARD_COLOR, font=FONT_SM))
        by = y0 + 114
        self.buttons.append(Button(10, by, 70, 32, "Cancel", self._cancel_bm_edit, font=FONT_SM))
        if self.bm_edit["idx"] is not None:
            self.buttons.append(Button(86, by, 70, 32, "Delete", self._delete_bookmark, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 86, by, 76, 32, "Save", self._save_bookmark, font=FONT_SM))

    def _focus_field(self, field):
        def handler():
            self.bm_edit["field"] = field
            self._rebuild()
        return handler

    def _cancel_bm_edit(self):
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _delete_bookmark(self):
        idx = self.bm_edit["idx"]
        if idx is not None and 0 <= idx < len(self.bookmarks):
            del self.bookmarks[idx]
            save_bookmarks(self.bookmarks)
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _save_bookmark(self):
        title = self.bm_edit["title"].strip() or "Untitled"
        url = self.bm_edit["url"].strip() or "https://"
        idx = self.bm_edit["idx"]
        if idx is None:
            self.bookmarks.append({"title": title, "url": url})
        else:
            self.bookmarks[idx] = {"title": title, "url": url}
        save_bookmarks(self.bookmarks)
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _bm_on_key(self, val):
        field = self.bm_edit["field"]
        maxlen = MAX_TITLE_LEN if field == "title" else MAX_URL_LEN
        if val == "BACKSPACE":
            self.bm_edit[field] = self.bm_edit[field][:-1]
        elif val == "ENTER":
            pass
        elif len(self.bm_edit[field]) < maxlen:
            self.bm_edit[field] += val

    # -- tap dispatch: keyboard modes, then chrome buttons, then links -------
    def on_tap(self, x, y):
        if self.mode == "type" and self.keyboard.on_tap(x, y, self._on_key):
            return True
        if self.mode == "bm_edit" and self.keyboard.on_tap(x, y, self._bm_on_key):
            return True
        if super().on_tap(x, y):
            return True
        if self.mode == "browse" and self._cur_entry() is not None:
            for (x0, y0, x1, y1, url) in self._link_hits:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    self._navigate(url, url)
                    return True
        return False

    # -- fetching + navigating -------------------------------------------------
    def _fetch_and_wrap(self, url):
        import requests
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Kos/1.0"})
        resp.raise_for_status()
        extractor = _TextExtractor()
        extractor.feed(resp.text)

        base = resp.url
        lines = _wrap_runs(extractor.chunks, CHARS_PER_LINE)
        resolved = [[(w, urljoin(base, u) if u else None) for (w, u) in line] for line in lines]
        pages = [resolved[i:i + LINES_PER_PAGE] for i in range(0, len(resolved), LINES_PER_PAGE)] or [[]]
        return pages, extractor.title

    def _navigate(self, title_hint, url):
        try:
            pages, page_title = self._fetch_and_wrap(url)
        except Exception as e:
            self.status = f"Couldn't load page: {e}"
            self._rebuild()
            return
        tab = self.tab
        entry = {"title": page_title or title_hint or url, "url": url, "pages": pages}
        tab["history"] = tab["history"][:tab["hist_index"] + 1]
        tab["history"].append(entry)
        tab["hist_index"] = len(tab["history"]) - 1
        tab["page_index"] = 0
        self.mode = "browse"
        self.status = None
        self._rebuild()

    def _build_page_buttons(self):
        footer_y = SCREEN_H - 46
        self.buttons.append(Button(8, footer_y, 100, 36, "New Tab", self._go_new_tab, font=FONT_SM))
        self.buttons.append(Button(114, footer_y, 90, 36, "Prev", self._prev_page, font=FONT_SM))
        self.buttons.append(Button(210, footer_y, 90, 36, "Next", self._next_page, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 66, footer_y, 56, 36, "Home", self.os.go_home, font=FONT_SM))

    def _go_new_tab(self):
        tab = self.tab
        tab["hist_index"] = -1
        self.mode = "browse"
        self._rebuild()

    def _prev_page(self):
        if self.tab["page_index"] > 0:
            self.tab["page_index"] -= 1

    def _next_page(self):
        entry = self._cur_entry()
        if entry and self.tab["page_index"] < len(entry["pages"]) - 1:
            self.tab["page_index"] += 1

    # -- drawing ----------------------------------------------------------------
    def _draw_tab_strip(self, draw):
        n = len(self.tabs)
        plus_w = 30
        tab_w = (SCREEN_W - plus_w) // n
        for i, t in enumerate(self.tabs):
            x = i * tab_w
            active = (i == self.active)
            bg = ACCENT if active else CARD_COLOR
            draw.rectangle([x, STATUS_BAR_H, x + tab_w - 2, STATUS_BAR_H + TAB_BAR_H], fill=bg)
            entry = self._cur_entry(t)
            label = entry["title"] if entry else "New Tab"
            if len(label) > 9:
                label = label[:8] + "\u2026"
            draw.text((x + 8, STATUS_BAR_H + TAB_BAR_H // 2), label, font=FONT_SM,
                       fill=(255, 255, 255), anchor="lm")
            if n > 1:
                draw.text((x + tab_w - 14, STATUS_BAR_H + TAB_BAR_H // 2), "\u2715",
                           font=FONT_SM, fill=(255, 255, 255), anchor="mm")
        draw.rectangle([SCREEN_W - plus_w, STATUS_BAR_H, SCREEN_W, STATUS_BAR_H + TAB_BAR_H],
                       fill=CARD_COLOR)
        draw.text((SCREEN_W - plus_w // 2, STATUS_BAR_H + TAB_BAR_H // 2), "+",
                   font=FONT_MD, fill=(255, 255, 255), anchor="mm")

    def _draw_omnibox(self, draw):
        y = STATUS_BAR_H + TAB_BAR_H
        tab = self.tab
        draw.rectangle([0, y, SCREEN_W, y + OMNIBOX_H], fill=(24, 24, 30))

        back_fill = FG_COLOR if tab["hist_index"] > 0 else (90, 90, 96)
        fwd_fill = FG_COLOR if tab["hist_index"] < len(tab["history"]) - 1 else (90, 90, 96)
        draw.text((19, y + OMNIBOX_H // 2), "\u2190", font=FONT_MD, fill=back_fill, anchor="mm")
        draw.text((55, y + OMNIBOX_H // 2), "\u2192", font=FONT_MD, fill=fwd_fill, anchor="mm")

        draw.rounded_rectangle([74, y + 5, SCREEN_W - 76, y + OMNIBOX_H - 5], radius=8, fill=CARD_COLOR)
        entry = self._cur_entry()
        url_text = entry["url"] if entry else "Search or type a URL"
        if len(url_text) > 30:
            url_text = url_text[:29] + "\u2026"
        draw.text((82, y + OMNIBOX_H // 2), url_text, font=FONT_SM,
                   fill=FG_COLOR if entry else (140, 140, 150), anchor="lm")

        is_bookmarked = entry is not None and any(b["url"] == entry["url"] for b in self.bookmarks)
        draw.text((SCREEN_W - 57, y + OMNIBOX_H // 2), "\u2605" if is_bookmarked else "\u2606",
                   font=FONT_MD, fill=ACCENT if is_bookmarked else FG_COLOR, anchor="mm")
        draw.text((SCREEN_W - 20, y + OMNIBOX_H // 2), "\u27F3", font=FONT_MD, fill=FG_COLOR, anchor="mm")

    def draw(self, draw, canvas):
        self._draw_tab_strip(draw)

        if self.mode == "type":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + TAB_BAR_H + 18), "Go to URL", font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            draw.rounded_rectangle([16, STATUS_BAR_H + TAB_BAR_H + 38, SCREEN_W - 16,
                                     STATUS_BAR_H + TAB_BAR_H + 78], radius=10, fill=CARD_COLOR)
            draw.text((24, STATUS_BAR_H + TAB_BAR_H + 58), self.draft_url, font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            for b in self.buttons:
                b.draw(draw)
            self.keyboard.draw(draw)
            return

        if self.mode == "bm_edit":
            y0 = STATUS_BAR_H + TAB_BAR_H + 8
            draw.text((SCREEN_W // 2, y0 + 4),
                       "Edit Bookmark" if self.bm_edit["idx"] is not None else "Add Bookmark",
                       font=FONT_MD, fill=(255, 255, 255), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            draw.text((24, y0 + 47), self.bm_edit["title"] or "Title", font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            draw.text((24, y0 + 89), self.bm_edit["url"] or "URL", font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            self.keyboard.draw(draw)
            return

        self._draw_omnibox(draw)
        entry = self._cur_entry()

        if entry is None:
            draw.text((SCREEN_W // 2, CONTENT_TOP + 20), "New Tab", font=FONT_LG,
                       fill=(255, 255, 255), anchor="mm")
            for b in self.buttons:
                if b.label in ("Edit", "Done"):
                    b.draw(draw)
            self._draw_bookmark_tiles(draw)
            if self.status:
                draw.text((SCREEN_W // 2, SCREEN_H - 60), self.status, font=FONT_SM,
                           fill=(150, 220, 150), anchor="mm")
            return

        self._link_hits = []
        y = CONTENT_TOP + 10
        page = entry["pages"][self.tab["page_index"]] if entry["pages"] else []
        for line in page:
            x = 14
            for word, url in line:
                color = LINK_COLOR if url else (220, 220, 230)
                w = draw.textlength(word + " ", font=FONT_SM)
                draw.text((x, y), word, font=FONT_SM, fill=color, anchor="lm")
                if url:
                    draw.line([x, y + 12, x + w - draw.textlength(" ", font=FONT_SM), y + 12],
                               fill=LINK_COLOR, width=1)
                    self._link_hits.append((x - 2, y - 8, x + w + 2, y + 12, url))
                x += w
            y += 21

        draw.text((SCREEN_W // 2, SCREEN_H - 64),
                   f"Page {self.tab['page_index'] + 1}/{len(entry['pages'])}", font=FONT_SM,
                   fill=(150, 150, 160), anchor="mm")
        if self.status:
            draw.text((SCREEN_W // 2, SCREEN_H - 82), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm")

        for b in self.buttons:
            b.draw(draw)

    def _draw_bookmark_tiles(self, draw):
        top = CONTENT_TOP + 8
        tile_top = top + 40
        cols = 3
        margin = 14
        cell = (SCREEN_W - margin * (cols + 1)) // cols
        items = list(self.bookmarks)
        for i, b in enumerate(items):
            r, c = divmod(i, cols)
            x = margin + c * (cell + margin)
            y = tile_top + r * (cell + margin)
            if y > SCREEN_H - 130:
                break
            draw.rounded_rectangle([x, y, x + cell, y + cell], radius=12, fill=CARD_COLOR)
            draw.text((x + cell // 2, y + cell // 2 - 10), "\U0001F310", font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            label = b["title"] if len(b["title"]) <= 12 else b["title"][:11] + "\u2026"
            draw.text((x + cell // 2, y + cell - 14), label, font=FONT_SM,
                       fill=(220, 220, 230), anchor="mm")

        for b in self.buttons:
            if b.label in ("\u270E", "+"):
                b.draw(draw)
