#!/usr/bin/env python3
import os, json, time, random, re, requests, threading
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BOT_TOKEN = "8054493496:AAH-Uu560wOuW-GV2KLrjGDwTMGUxH0_5wg"
TONY_ID = "8685464868"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Playwright semaphore: max 1 Chromium at a time
BROWSER_SEM = threading.Semaphore(1)

CATEGORIES = {
    '\u7384\u5e7b': 'xuanhuan', '\u5947\u5e7b': 'xuanhuan',
    '\u6b66\u4fe0': 'xianxia', '\u4ed9\u4fa0': 'xianxia',
    '\u6b77\u53f2': 'lishi', '\u8ecd\u4e8b': 'lishi',
    '\u79d1\u5e7b': 'wangyou', '\u672a\u4f86': 'wangyou',
    '\u9748\u7570': 'lingyi',
    '\u90fd\u5e02': 'dushi',
}

EXCLUDE_KEYWORDS = [
    '\u8012\u7f8e', 'BL', '\u8a00\u60c5', '\u611b\u60c5', '\u5305\u990a',
    '\u653b\u00d7\u53d7', '\u91d1\u4e3b', '\u8150', '\u9aa8\u79d1',
    '\u7236\u5973', '\u7236\u5b50', '\u96d9\u6027',
]

user_state = {}
download_status = {}
PAGE_SIZE = 8


# ── Telegram API ──────────────────────────────────────────────

def send(chat_id, text, parse_mode='HTML', reply_markup=None):
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(f"{API}/sendMessage", data=data, timeout=10)
    except Exception:
        pass

def edit_message(chat_id, message_id, text, parse_mode='HTML', reply_markup=None):
    data = {'chat_id': chat_id, 'message_id': message_id,
            'text': text, 'parse_mode': parse_mode}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    try:
        requests.post(f"{API}/editMessageText", data=data, timeout=10)
    except Exception:
        pass

def answer_callback(callback_id, text=''):
    try:
        requests.post(f"{API}/answerCallbackQuery",
            data={'callback_query_id': callback_id, 'text': text}, timeout=10)
    except Exception:
        pass

def send_file(chat_id, path, caption):
    with open(path, 'rb') as f:
        requests.post(f"{API}/sendDocument",
            data={'chat_id': chat_id, 'caption': caption},
            files={'document': f}, timeout=120)


# ── Browser (with semaphore) ──────────────────────────────────

def get_browser():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        locale='zh-TW')
    return p, browser, ctx

def get_html(url, wait=8):
    with BROWSER_SEM:
        p, browser, ctx = get_browser()
        try:
            page = ctx.new_page()
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(wait)
            return page.content()
        finally:
            browser.close()
            p.stop()

def parse_content(html):
    soup = BeautifulSoup(html, 'html.parser')
    content = soup.find('div', class_='content') or soup.find('div', id='content')
    if not content:
        return None
    for tag in content.find_all(['script', 'style', 'ins']):
        tag.decompose()
    lines = [l for l in content.get_text('\n').split('\n')
             if l.strip() and 'czbooks' not in l]
    return '\n'.join(lines)


# ── Tools ──────────────────────────────────────────────────

def is_excluded(title):
    return any(kw in title for kw in EXCLUDE_KEYWORDS)

def clean_title(title):
    t = title.strip()
    # Skip if it's just a status label
    skip = ['\u5df2\u5b8c\u7d50', '\u9023\u8f09\u4e2d', '\u5df2\u5b8c\u7d50..']
    return None if t in skip or len(t) < 2 else t

def parse_czbooks_links(soup, limit=20):
    results, seen = [], set()
    for a in soup.find_all('a', href=re.compile(r'//czbooks\.net/n/[^/]+$')):
        href = a.get('href', '')
        raw_title = a.text.strip()
        title = clean_title(raw_title)
        if not title or href in seen or is_excluded(title):
            continue
        seen.add(href)
        parent_text = a.parent.get_text() if a.parent else ''
        done = '\u5df2\u5b8c\u7d50' in parent_text or '\u5b8c\u7d50' in title
        results.append({'title': title, 'url': 'https:' + href, 'done': done, 'source': 'czbooks'})
        if len(results) >= limit:
            break
    return results


# ── czbooks ────────────────────────────────────────────────

def get_hot_list(category=None, sort='', limit=20):
    if category and category in CATEGORIES:
        url = f"https://czbooks.net/c/{CATEGORIES[category]}"
        if sort:
            url += f"/{sort}"
    else:
        url = "https://czbooks.net/"
    html = get_html(url, wait=7)
    return parse_czbooks_links(BeautifulSoup(html, 'html.parser'), limit)

def get_weekly_rank(limit=20):
    results, seen = [], set()
    for cat in ['xuanhuan', 'xianxia', 'lishi', 'dushi', 'lingyi']:
        if len(results) >= limit:
            break
        try:
            html = get_html(f"https://czbooks.net/c/{cat}/weekly", wait=6)
            for r in parse_czbooks_links(BeautifulSoup(html, 'html.parser'), limit):
                if r['url'] not in seen:
                    seen.add(r['url'])
                    results.append(r)
        except Exception:
            continue
    return results[:limit]

def search_complete(limit=20):
    results, seen = [], set()
    for cat in ['xuanhuan', 'xianxia', 'lishi', 'dushi', 'lingyi', 'wangyou']:
        if len(results) >= limit:
            break
        try:
            html = get_html(f"https://czbooks.net/c/{cat}/total", wait=6)
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=re.compile(r'//czbooks\.net/n/[^/]+$')):
                href = a.get('href', '')
                raw_title = a.text.strip()
                title = clean_title(raw_title)
                if not title or href in seen or is_excluded(title):
                    continue
                parent_text = a.parent.get_text() if a.parent else ''
                if '\u5df2\u5b8c\u7d50' not in parent_text and '\u5b8c\u7d50' not in title:
                    continue
                seen.add(href)
                results.append({'title': title, 'url': 'https:' + href, 'done': True, 'source': 'czbooks'})
                if len(results) >= limit:
                    break
        except Exception:
            continue
    return results

def search_novels(keyword, limit=20):
    html = get_html(f"https://czbooks.net/s/{requests.utils.quote(keyword)}", wait=7)
    return parse_czbooks_links(BeautifulSoup(html, 'html.parser'), limit)

def parse_book_info(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    title_match = re.search(r'\u300a(.+?)\u300b', soup.title.text if soup.title else '')
    title = title_match.group(1) if title_match else '\u672a\u77e5\u66f8\u540d'
    author_el = soup.find('a', href=re.compile(r'/a/'))
    author = author_el.text.strip() if author_el else '\u672a\u77e5\u4f5c\u8005'
    # Intro: try meta description first
    intro = '\uff08\u7121\u7c21\u4ecb\uff09'
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta and meta.get('content') and len(meta['content']) > 20:
        intro = meta['content'][:200]
    else:
        for el in soup.find_all(['p', 'div']):
            text = el.get_text().strip()
            if 50 < len(text) < 500 and not el.find('a') and not el.find('ul'):
                if any(s in text for s in ['\u71b1\u9580\u641c\u5c0b', '\u767b\u5165', 'Facebook']):
                    continue
                intro = text[:200]
                break
    # Tags: avoid hot search sidebar
    hot_pos = html.find('\u71b1\u9580\u641c\u5c0b')
    tags = []
    for a in soup.find_all('a', href=re.compile(r'/hashtag/')):
        tag = a.text.strip()
        if not tag or len(tag) > 8:
            continue
        tag_pos = html.find(tag)
        if hot_pos > 0 and tag_pos >= hot_pos:
            continue
        tags.append(tag)
        if len(tags) >= 5:
            break
    status = '\u2705 \u5df2\u5b8c\u7d50' if '\u5df2\u5b8c\u7d50' in html else '\ud83d\udd04 \u9023\u8f09\u4e2d'
    book_id = url.rstrip('/').split('/')[-1]
    chapters = len(soup.find_all('a', href=re.compile(rf'/n/{book_id}/')))
    return {'title': title, 'author': author, 'intro': intro,
            'tags': tags, 'status': status, 'chapters': chapters,
            'url': url, 'source': 'czbooks'}

def format_czbooks_card(info):
    tags_str = ' \u00b7 '.join(info['tags']) if info['tags'] else '\u7121\u6a19\u7c64'
    return (f"\ud83d\udcd6 <b>\u300a{info['title']}\u300b</b>\n"
            f"\ud83d\udc64 {info['author']}\n"
            f"\ud83c\udff7\ufe0f {tags_str}\n"
            f"\ud83d\udcca {info['status']} \u00b7 {info['chapters']} \u7ae0\n\n"
            f"\ud83d\udcdd {info['intro']}")


# ── zxcs.zip ──────────────────────────────────────────────────

ZXCS_HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'}

def zxcs_get(url):
    r = requests.get(url, headers=ZXCS_HDR, timeout=15)
    r.encoding = 'utf-8'
    return r.text

def zxcs_parse_list(html, limit=20):
    soup = BeautifulSoup(html, 'html.parser')
    results, seen = [], set()
    for a in soup.find_all('a', href=re.compile(r'/book/\d+\.html')):
        raw = a.get_text().strip()
        title = re.sub(r'[\uff08(][^\uff09)]*[\uff09)]', '', raw).strip()
        if not title or len(title) < 2 or title in seen:
            continue
        seen.add(title)
        book_url = 'https://zxcs.zip' + a['href'] if a['href'].startswith('/') else a['href']
        results.append({'title': title, 'url': book_url, 'done': True, 'source': 'zxcs'})
        if len(results) >= limit:
            break
    return results

def zxcs_rank(rank_type='topdownload', limit=20):
    return zxcs_parse_list(zxcs_get(f"https://zxcs.zip/rank/{rank_type}"), limit)

def zxcs_recommend(limit=20):
    return zxcs_parse_list(zxcs_get("https://zxcs.zip/recommend"), limit)

def zxcs_search(keyword, limit=20):
    results = zxcs_parse_list(zxcs_get(f"https://zxcs.zip/search?q={requests.utils.quote(keyword)}"), limit)
    if not results:
        results = zxcs_parse_list(zxcs_get(f"https://zxcs.zip/?s={requests.utils.quote(keyword)}"), limit)
    return results

def zxcs_book_info(url):
    html = zxcs_get(url)
    soup = BeautifulSoup(html, 'html.parser')
    h2 = soup.find('h2')
    title = re.sub(r'[\uff08(][^\uff09)]*[\uff09)]', '', h2.get_text().strip() if h2 else '\u672a\u77e5').strip()
    author = re.search(r'\u3010\u4f5c\u8005\u3011\uff1a?\s*(.+)', html)
    author = author.group(1).strip() if author else '\u672a\u77e5\u4f5c\u8005'
    size = re.search(r'\u3010\u5b57\u6570\u3011\uff1a?\s*(.+)', html)
    size = size.group(1).strip() if size else '?'
    size_txt = re.search(r'\u3010TXT\u5927\u5c0f\u3011\uff1a?\s*(.+)', html)
    size_txt = size_txt.group(1).strip() if size_txt else '?'
    cat = re.search(r'\u3010\u5206\u7c7b\u3011\uff1a?\s*(.+)', html)
    cat = cat.group(1).strip() if cat else ''
    intro = re.search(r'\u3010\u5185\u5bb9\u7b80\u4ecb\u3011\uff1a?\s*([\s\S]+?)(?=\u3010|---)', html)
    intro = intro.group(1).strip()[:200] if intro else '\uff08\u7121\u7c21\u4ecb\uff09'
    dl_link = None
    for a in soup.find_all('a', href=re.compile(r'download\.zxcs\.zip')):
        dl_link = a['href']
        break
    return {'title': title, 'author': author, 'intro': intro,
            'size': size, 'size_txt': size_txt, 'cat': cat,
            'url': url, 'dl_link': dl_link, 'source': 'zxcs'}

def format_zxcs_card(info):
    return (f"\ud83d\udcda <b>\u300a{info['title']}\u300b</b>\n"
            f"\ud83d\udc64 {info['author']}\n"
            f"\ud83d\udcc2 {info['cat']}\n"
            f"\ud83d\udcdd {info['size']} \u5b57 \u00b7 TXT {info['size_txt']}\n"
            f"\u2705 \u7cbe\u6821\u5b8c\u672c\n\n"
            f"\ud83d\udcd6 {info['intro']}")

def zxcs_download(chat_id, info):
    key = f"{chat_id}_{info['title']}"
    download_status[key] = {'title': info['title'], 'done': False}
    send(chat_id, f"\u23f3 \u4e0b\u8f09\u300a{info['title']}\u300b\u7cbe\u6821 TXT...")
    try:
        dl_url = info.get('dl_link')
        if not dl_url:
            send(chat_id, "\u274c \u627e\u4e0d\u5230\u4e0b\u8f09\u9023\u7d50")
            return
        r = requests.get(dl_url, headers=ZXCS_HDR, timeout=60, stream=True)
        if r.status_code != 200:
            send(chat_id, f"\u274c \u4e0b\u8f09\u5931\u6557 HTTP {r.status_code}")
            return
        os.makedirs(os.path.expanduser("~/novels"), exist_ok=True)
        safe = re.sub(r'[^\w\u4e00-\u9fff]+', '_', info['title'])
        out = os.path.expanduser(f"~/novels/zxcs_{safe}.txt")
        with open(out, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = os.path.getsize(out) // 1024
        send_file(chat_id, out, f"\u2705 \u300a{info['title']}\u300b\u7cbe\u6821\u5b8c\u672c\n{info['author']} \u00b7 {size_kb} KB\n(\u77e5\u8ecd\u85cf\u66f8)")
    except Exception as e:
        send(chat_id, f"\u274c \u4e0b\u8f09\u5931\u6557\uff1a{e}")
    finally:
        download_status.pop(key, None)


# ── czbooks download ───────────────────────────────────────────

def download_czbooks(chat_id, url, title):
    key = f"{chat_id}_{title}"
    download_status[key] = {'title': title, 'current': 0, 'total': 0, 'done': False, 'failed': 0}
    send(chat_id, f"\u23f3 \u958b\u59cb\u4e0b\u8f09\u300a{title}\u300b\n\u5b8c\u6210\u5f8c\u50b3 TXT\uff0c\u6bcf 500 \u7ae0\u56de\u5831")
    try:
        with BROWSER_SEM:
            p, browser, ctx = get_browser()
            page = ctx.new_page()
            page.goto("https://czbooks.net", timeout=60000, wait_until="domcontentloaded")
            time.sleep(6)
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            time.sleep(8)
            book_id = url.rstrip('/').split('/')[-1]
            links = page.query_selector_all(f'a[href*="/n/{book_id}/"]')
            chapters = []
            for link in links:
                href = link.get_attribute('href')
                text = link.inner_text().strip()
                if href and text and '\u4ed8\u8cbb' not in text:
                    ch_url = 'https:' + href if href.startswith('//') else 'https://czbooks.net' + href
                    chapters.append({'title': text, 'url': ch_url})
            total = len(chapters)
            download_status[key]['total'] = total
            os.makedirs(os.path.expanduser("~/novels"), exist_ok=True)
            safe = re.sub(r'[^\w\u4e00-\u9fff]+', '_', title)
            out = os.path.expanduser(f"~/novels/{safe}.txt")
            with open(out, 'w', encoding='utf-8') as f:
                f.write(f"\u300a{title}\u300b\n{'='*40}\n\n")
            failed = 0
            for i, ch in enumerate(chapters):
                content = None
                retry = 0
                while content is None and retry < 3:
                    try:
                        page.goto(ch['url'], timeout=45000, wait_until="domcontentloaded")
                        time.sleep(2)
                        html = page.content()
                        if 'Just a moment' in html:
                            browser.close()
                            p2, browser, ctx = get_browser()
                            page = ctx.new_page()
                            page.goto("https://czbooks.net", timeout=60000, wait_until="domcontentloaded")
                            time.sleep(8)
                            retry += 1
                            continue
                        content = parse_content(html)
                        if not content:
                            retry += 1
                            time.sleep(2)
                    except Exception:
                        retry += 1
                        time.sleep(3)
                        try:
                            browser.close()
                        except Exception:
                            pass
                        p2, browser, ctx = get_browser()
                        page = ctx.new_page()
                        page.goto("https://czbooks.net", timeout=60000, wait_until="domcontentloaded")
                        time.sleep(6)
                with open(out, 'a', encoding='utf-8') as f:
                    f.write(f"\n\n{'='*20}\n{ch['title']}\n{'='*20}\n\n" +
                        (content if content else '[\u6293\u53d6\u5931\u6557]'))
                if not content:
                    failed += 1
                download_status[key]['current'] = i + 1
                download_status[key]['failed'] = failed
                if (i + 1) % 500 == 0:
                    send(chat_id, f"\u23f3 \u300a{title}\u300b\u9032\u5ea6\uff1a{i+1}/{total} \u7ae0")
                time.sleep(random.uniform(1.5, 2.5))
            browser.close()
            p.stop()
        size_kb = os.path.getsize(out) // 1024
        caption = f"\u2705 \u300a{title}\u300b\u5b8c\u6210\n\u5171 {total} \u7ae0 \u00b7 {size_kb} KB"
        if failed:
            caption += f"\n\u26a0\ufe0f {failed} \u7ae0\u5931\u6557"
        send_file(chat_id, out, caption)
    except Exception as e:
        send(chat_id, f"\u274c \u4e0b\u8f09\u5931\u6557\uff1a{e}")
    finally:
        download_status.pop(key, None)


# ── Keyboards ─────────────────────────────────────────────────

def make_list_keyboard(results, page=0):
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(results))
    total_pages = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
    buttons = []
    for i, r in enumerate(results[start:end]):
        icon = '\ud83d\udcda' if r.get('source') == 'zxcs' else ('\u2705' if r['done'] else '\ud83d\udd04')
        buttons.append([{'text': f"{icon} {r['title'][:22]}", 'callback_data': f"book_{start+i}"}])
    nav = []
    if page > 0:
        nav.append({'text': '\u2b05\ufe0f \u4e0a\u4e00\u9801', 'callback_data': f"page_{page-1}"})
    if end < len(results):
        nav.append({'text': '\u4e0b\u4e00\u9801 \u27a1\ufe0f', 'callback_data': f"page_{page+1}"})
    if nav:
        buttons.append(nav)
    if total_pages > 1:
        buttons.append([{'text': f'\u7b2c {page+1}/{total_pages} \u9801', 'callback_data': 'noop'}])
    buttons.append([{'text': '\u274c \u53d6\u6d88', 'callback_data': 'cancel'}])
    return {'inline_keyboard': buttons}

def make_confirm_keyboard(source='czbooks'):
    dl = '\ud83d\udce5 \u4e0b\u8f09\u7cbe\u6821 TXT' if source == 'zxcs' else '\ud83d\udce5 \u78ba\u8a8d\u4e0b\u8f09'
    return {'inline_keyboard': [
        [{'text': dl, 'callback_data': 'confirm_download'}],
        [{'text': '\ud83d\udd19 \u8fd4\u56de', 'callback_data': 'back'},
         {'text': '\u274c \u53d6\u6d88', 'callback_data': 'cancel'}]
    ]}

def make_zxcs_menu():
    return {'inline_keyboard': [
        [{'text': '\u2b07\ufe0f \u4e0b\u8f09\u6392\u884c', 'callback_data': 'zxcs_topdownload'},
         {'text': '\u2b50 \u4ed9\u8349\u6392\u884c', 'callback_data': 'zxcs_toppraise'}],
        [{'text': '\ud83d\udcd6 \u66f8\u8352\u63a8\u85a6', 'callback_data': 'zxcs_recommend'}],
        [{'text': '\ud83d\udd0d \u641c\u66f8\u540d', 'callback_data': 'zxcs_search'}],
        [{'text': '\u274c \u53d6\u6d88', 'callback_data': 'cancel'}]
    ]}

def make_main_keyboard():
    return {'keyboard': [
        ['\ud83d\udd25 \u71b1\u9580\u699c', '\u2705 \u5b8c\u672c\u71b1\u9580', '\u2b50 \u9031\u6392\u884c'],
        ['\u7384\u5e7b', '\u6b66\u4fe0', '\u6b77\u53f2'],
        ['\u79d1\u5e7b', '\u9748\u7570', '\u90fd\u5e02'],
        ['\ud83d\udcda \u77e5\u8ecd\u85cf\u66f8', '/status', '/cancel'],
    ], 'resize_keyboard': True}


# ── Show results ───────────────────────────────────────────────

def show_results(chat_id, results, title_text, page=0, message_id=None):
    if not results:
        if message_id:
            edit_message(chat_id, message_id, "\u274c \u627e\u4e0d\u5230\u7d50\u679c")
        else:
            send(chat_id, "\u274c \u627e\u4e0d\u5230\u7d50\u679c\uff0c\u8a66\u8a66\u4e0d\u540c\u95dc\u9375\u5b57")
        return
    msg = f"{title_text}\uff08\u5171 {len(results)} \u672c\uff09\n\u9ede\u9078\u66f8\u540d\u67e5\u770b\u8a73\u60c5\uff1a"
    kb = make_list_keyboard(results, page)
    if message_id:
        edit_message(chat_id, message_id, msg, reply_markup=kb)
    else:
        send(chat_id, msg, reply_markup=kb)
    user_state[chat_id] = {'action': 'select', 'results': results, 'page': page, 'title': title_text}


# ── Message handler ────────────────────────────────────────────

def handle_message(msg):
    chat_id = str(msg['chat']['id'])
    text = msg.get('text', '').strip()
    if not text or chat_id != TONY_ID:
        if chat_id != TONY_ID:
            send(chat_id, "\u26d4 \u79c1\u4eba\u6a5f\u5668\u4eba")
        return

    if text in ['/start', '/help']:
        send(chat_id,
            "\ud83d\udcda <b>\u5c0f\u8aaa\u4e0b\u8f09\u6a5f\u5668\u4eba</b>\n\n"
            "\u2022 \u76f4\u63a5\u8f38\u5165\u66f8\u540d \u2192 \u641c\u5c0b\n"
            "\u2022 \ud83d\udcda \u77e5\u8ecd\u85cf\u66f8 \u2192 \u7cbe\u6821\u5b8c\u672c TXT\n"
            "\u2022 /status \u2192 \u67e5\u770b\u4e0b\u8f09\u9032\u5ea6\n"
            "\u2022 /cancel \u2192 \u53d6\u6d88",
            reply_markup=make_main_keyboard())
        return

    if text == '/cancel':
        user_state.pop(chat_id, None)
        send(chat_id, "\u2705 \u5df2\u53d6\u6d88", reply_markup=make_main_keyboard())
        return

    if text == '/status':
        active = {k: v for k, v in download_status.items() if k.startswith(chat_id)}
        if not active:
            send(chat_id, "\ud83d\udced \u76ee\u524d\u6c92\u6709\u9032\u884c\u4e2d\u7684\u4e0b\u8f09")
        else:
            out = "\ud83d\udcca <b>\u4e0b\u8f09\u9032\u5ea6</b>\n\n"
            for k, s in active.items():
                pct = f"{s.get('current',0)}/{s.get('total',0)}" if s.get('total') else '\u6e96\u5099\u4e2d'
                out += f"\ud83d\udcd6 \u300a{s['title']}\u300b\n\u9032\u5ea6\uff1a{pct} \u7ae0\n"
            send(chat_id, out)
        return

    state = user_state.get(chat_id, {})

    if state.get('action') == 'zxcs_search_input':
        user_state.pop(chat_id, None)
        kw = text
        send(chat_id, f"\ud83d\udd0d \u77e5\u8ecd\u641c\u5c0b\u300c{kw}\u300d\u4e2d...")
        threading.Thread(target=lambda: show_results(
            chat_id, zxcs_search(kw), f"\ud83d\udcda \u77e5\u8ecd\u300c{kw}\u300d"), daemon=True).start()
        return

    hot = '\ud83d\udd25 \u71b1\u9580\u699c'
    complete = '\u2705 \u5b8c\u672c\u71b1\u9580'
    weekly = '\u2b50 \u9031\u6392\u884c'
    zxcs = '\ud83d\udcda \u77e5\u8ecd\u85cf\u66f8'

    if text == hot:
        send(chat_id, "\u23f3 \u53d6\u5f97\u71b1\u9580\u699c...")
        threading.Thread(target=lambda: show_results(
            chat_id, get_hot_list(), "\ud83d\udd25 \u71b1\u9580\u699c"), daemon=True).start()
        return
    if text == complete:
        send(chat_id, "\u23f3 \u641c\u5c0b\u5b8c\u672c\u5c0f\u8aaa...")
        threading.Thread(target=lambda: show_results(
            chat_id, search_complete(), "\u2705 \u5b8c\u672c\u5c0f\u8aaa"), daemon=True).start()
        return
    if text == weekly:
        send(chat_id, "\u23f3 \u53d6\u5f97\u9031\u6392\u884c...")
        threading.Thread(target=lambda: show_results(
            chat_id, get_weekly_rank(), "\u2b50 \u9031\u6392\u884c"), daemon=True).start()
        return
    if text == zxcs:
        send(chat_id, "\ud83d\udcda <b>\u77e5\u8ecd\u85cf\u66f8</b>\n\u7cbe\u6821\u5b8c\u672c TXT\n\n\u8acb\u9078\u64c7\u529f\u80fd\uff1a",
            reply_markup=make_zxcs_menu())
        return
    if text in CATEGORIES:
        cat = text
        send(chat_id, f"\u23f3 \u53d6\u5f97\u300c{cat}\u300d\u71b1\u9580...")
        threading.Thread(target=lambda: show_results(
            chat_id, get_hot_list(cat), f"\ud83d\udd25 {cat} \u71b1\u9580"), daemon=True).start()
        return

    send(chat_id, f"\ud83d\udd0d \u641c\u5c0b\u300c{text}\u300d\u4e2d...")
    threading.Thread(target=lambda: show_results(
        chat_id, search_novels(text), f"\ud83d\udcda \u300c{text}\u300d\u641c\u5c0b\u7d50\u679c"), daemon=True).start()


# ── Callback handler ───────────────────────────────────────────

def handle_callback(cb):
    chat_id = str(cb['message']['chat']['id'])
    message_id = cb['message']['message_id']
    data = cb.get('data', '')
    cb_id = cb['id']
    if chat_id != TONY_ID:
        answer_callback(cb_id, "\u26d4 \u79c1\u4eba\u6a5f\u5668\u4eba")
        return
    answer_callback(cb_id)
    if data == 'noop':
        return
    if data == 'cancel':
        user_state.pop(chat_id, None)
        edit_message(chat_id, message_id, "\u2705 \u5df2\u53d6\u6d88")
        return

    state = user_state.get(chat_id, {})

    if data == 'zxcs_topdownload':
        edit_message(chat_id, message_id, "\u23f3 \u53d6\u5f97\u77e5\u8ecd\u4e0b\u8f09\u6392\u884c...")
        threading.Thread(target=lambda: show_results(
            chat_id, zxcs_rank('topdownload'), "\ud83d\udcda \u77e5\u8ecd \u4e0b\u8f09\u6392\u884c", message_id=message_id), daemon=True).start()
        return
    if data == 'zxcs_toppraise':
        edit_message(chat_id, message_id, "\u23f3 \u53d6\u5f97\u4ed9\u8349\u6392\u884c...")
        threading.Thread(target=lambda: show_results(
            chat_id, zxcs_rank('toppraise'), "\ud83d\udcda \u77e5\u8ecd \u4ed9\u8349\u6392\u884c", message_id=message_id), daemon=True).start()
        return
    if data == 'zxcs_recommend':
        edit_message(chat_id, message_id, "\u23f3 \u53d6\u5f97\u66f8\u8352\u63a8\u85a6...")
        threading.Thread(target=lambda: show_results(
            chat_id, zxcs_recommend(), "\ud83d\udcda \u77e5\u8ecd \u66f8\u8352\u63a8\u85a6", message_id=message_id), daemon=True).start()
        return
    if data == 'zxcs_search':
        edit_message(chat_id, message_id, "\ud83d\udd0d \u8acb\u8f38\u5165\u8981\u641c\u5c0b\u7684\u66f8\u540d\uff1a")
        user_state[chat_id] = {'action': 'zxcs_search_input'}
        return

    if data.startswith('page_') and state.get('action') == 'select':
        page = int(data.split('_')[1])
        results = state.get('results', [])
        title_text = state.get('title', '')
        edit_message(chat_id, message_id,
            f"{title_text}\uff08\u5171 {len(results)} \u672c\uff09\n\u9ede\u9078\u66f8\u540d\u67e5\u770b\u8a73\u60c5\uff1a",
            reply_markup=make_list_keyboard(results, page))
        user_state[chat_id]['page'] = page
        return

    if data.startswith('book_') and state.get('action') == 'select':
        idx = int(data.split('_')[1])
        results = state.get('results', [])
        if 0 <= idx < len(results):
            book = results[idx]
            source = book.get('source', 'czbooks')
            user_state[chat_id] = {'action': 'confirm', 'book': book}
            edit_message(chat_id, message_id, f"\u23f3 \u8b80\u53d6\u300a{book['title']}\u300b\u8a73\u60c5...")
            if source == 'zxcs':
                def load_zxcs():
                    try:
                        info = zxcs_book_info(book['url'])
                        user_state[chat_id] = {'action': 'confirm', 'book': info}
                        edit_message(chat_id, message_id, format_zxcs_card(info),
                            reply_markup=make_confirm_keyboard('zxcs'))
                    except Exception as e:
                        edit_message(chat_id, message_id, f"\u274c \u8b80\u53d6\u5931\u6557\uff1a{e}")
                threading.Thread(target=load_zxcs, daemon=True).start()
            else:
                def load_czbooks():
                    try:
                        html = get_html(book['url'])
                        info = parse_book_info(html, book['url'])
                        user_state[chat_id] = {'action': 'confirm', 'book': info}
                        edit_message(chat_id, message_id, format_czbooks_card(info),
                            reply_markup=make_confirm_keyboard('czbooks'))
                    except Exception as e:
                        edit_message(chat_id, message_id, f"\u274c \u8b80\u53d6\u5931\u6557\uff1a{e}")
                threading.Thread(target=load_czbooks, daemon=True).start()
        return

    if data == 'confirm_download' and state.get('action') == 'confirm':
        book = state.get('book', {})
        user_state.pop(chat_id, None)
        source = book.get('source', 'czbooks')
        edit_message(chat_id, message_id,
            f"\ud83d\udce5 \u5df2\u52a0\u5165\u4e0b\u8f09\n\u300a{book['title']}\u300b\n\n/status \u67e5\u770b\u9032\u5ea6")
        if source == 'zxcs':
            threading.Thread(target=zxcs_download, args=(chat_id, book), daemon=True).start()
        else:
            threading.Thread(target=download_czbooks,
                args=(chat_id, book['url'], book['title']), daemon=True).start()
        return

    if data == 'back':
        user_state.pop(chat_id, None)
        edit_message(chat_id, message_id, "\u5df2\u8fd4\u56de\uff0c\u8acb\u91cd\u65b0\u641c\u5c0b\u6216\u9078\u5206\u985e")


# ── Main loop ─────────────────────────────────────────────────

def clear_old_updates():
    """Clear pending updates on startup to avoid processing stale messages"""
    try:
        r = requests.get(f"{API}/getUpdates", params={'offset': -1, 'timeout': 0}, timeout=5)
        data = r.json()
        if data.get('result'):
            last_id = data['result'][-1]['update_id']
            requests.get(f"{API}/getUpdates", params={'offset': last_id + 1, 'timeout': 0}, timeout=5)
            print(f"Cleared updates up to {last_id}")
    except Exception as e:
        print(f"Warning: could not clear updates: {e}")

def run():
    print("Novel Bot v4 started - stable polling")
    clear_old_updates()
    offset = 0
    while True:
        try:
            r = requests.get(f"{API}/getUpdates",
                params={'offset': offset, 'timeout': 20}, timeout=25)
            for u in r.json().get('result', []):
                offset = u['update_id'] + 1
                if 'message' in u:
                    threading.Thread(target=handle_message,
                        args=(u['message'],), daemon=True).start()
                elif 'callback_query' in u:
                    threading.Thread(target=handle_callback,
                        args=(u['callback_query'],), daemon=True).start()
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    run()
