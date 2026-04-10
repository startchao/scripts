#!/usr/bin/env python3
import os, json, time, random, re, requests, threading
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BOT_TOKEN = "8054493496:AAFCKGXWeFaTrHng7luMy7vk8N0nTJ0UYhw"
TONY_ID = "8685464868"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CATEGORIES = {
    '玄幻': 'xuanhuan', '奇幻': 'xuanhuan',
    '武俠': 'xianxia', '仙俠': 'xianxia',
    '歷史': 'lishi', '軍事': 'lishi',
    '科幻': 'wangyou', '未來': 'wangyou',
    '靈異': 'lingyi',
    '都市': 'dushi',
}

EXCLUDE_KEYWORDS = [
    '耽美', 'BL', '言情', '愛情', '包養', '重生戀愛',
    '攻X受', '攻×受', '金主', '腐', '1v1限',
    '骨科', '父女', '父子', '雙性',
]

user_state = {}
download_status = {}  # 追蹤下載進度


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


# ── 工具函式 ──────────────────────────────────────────────────

def is_excluded(title, tags_text=''):
    combined = title + tags_text
    return any(kw in combined for kw in EXCLUDE_KEYWORDS)

def get_browser():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        locale='zh-TW')
    return p, browser, ctx

def get_html(url, wait=8):
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
             if l.strip() and 'czbooks' not in l and '小說狂人' not in l]
    return '\n'.join(lines)


# ── 搜尋 / 熱門 ───────────────────────────────────────────────

def get_hot_list(category=None, limit=10):
    url = f"https://czbooks.net/c/{CATEGORIES[category]}" if category and category in CATEGORIES else "https://czbooks.net/"
    html = get_html(url, wait=7)
    soup = BeautifulSoup(html, 'html.parser')
    results, seen = [], set()
    for a in soup.find_all('a', href=re.compile(r'//czbooks\.net/n/[^/]+$')):
        href = a.get('href', '')
        title = a.text.strip()
        if not title or len(title) < 2 or href in seen:
            continue
        if title in ['已完結', '連載中'] or is_excluded(title):
            continue
        seen.add(href)
        parent_text = a.parent.get_text() if a.parent else ''
        done = '已完結' in parent_text or '完結' in title
        results.append({'title': title, 'url': 'https:' + href, 'done': done})
        if len(results) >= limit:
            break
    return results

def search_novels(keyword, complete_only=False, limit=20):
    url = f"https://czbooks.net/s/{requests.utils.quote(keyword)}"
    html = get_html(url, wait=7)
    soup = BeautifulSoup(html, 'html.parser')
    results, seen = [], set()
    for a in soup.find_all('a', href=re.compile(r'//czbooks\.net/n/[^/]+$')):
        href = a.get('href', '')
        title = a.text.strip()
        if not title or len(title) < 2 or href in seen:
            continue
        if title in ['已完結', '連載中'] or is_excluded(title):
            continue
        seen.add(href)
        parent_text = a.parent.get_text() if a.parent else ''
        done = '已完結' in parent_text or '完結' in title
        if complete_only and not done:
            continue
        results.append({'title': title, 'url': 'https:' + href, 'done': done})
        if len(results) >= limit:
            break
    return results

def search_complete(limit=20):
    """專門搜尋完本小說"""
    keywords = ['完結', '已完結', '完本']
    results, seen = [], set()
    for kw in keywords:
        url = f"https://czbooks.net/s/{requests.utils.quote(kw)}"
        html = get_html(url, wait=7)
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'//czbooks\.net/n/[^/]+$')):
            href = a.get('href', '')
            title = a.text.strip()
            if not title or len(title) < 2 or href in seen:
                continue
            if title in ['已完結', '連載中'] or is_excluded(title):
                continue
            seen.add(href)
            results.append({'title': title, 'url': 'https:' + href, 'done': True})
            if len(results) >= limit:
                return results
    return results


# ── 書本詳情 ──────────────────────────────────────────────────

def parse_book_info(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    title_match = re.search(r'《(.+?)》', soup.title.text if soup.title else '')
    title = title_match.group(1) if title_match else '未知書名'
    author_el = soup.find('a', href=re.compile(r'/a/'))
    author = author_el.text.strip() if author_el else '未知作者'
    intro = '（無簡介）'
    for el in soup.find_all(['p', 'div']):
        text = el.get_text().strip()
        if 30 < len(text) < 500 and not el.find('a'):
            parent_text = str(el.parent)
            if 'intro' in parent_text or 'desc' in parent_text or '簡介' in parent_text:
                intro = text[:200]
                break
    # 過濾掉太長的標籤（網站熱門標籤）
    tags = [a.text.strip() for a in soup.find_all('a', href=re.compile(r'/hashtag/'))
            if len(a.text.strip()) <= 8][:5]
    status = '✅ 已完結' if '已完結' in html else '🔄 連載中'
    book_id = url.rstrip('/').split('/')[-1]
    chapter_links = soup.find_all('a', href=re.compile(rf'/n/{book_id}/'))
    chapters = len(chapter_links)
    return {
        'title': title, 'author': author, 'intro': intro,
        'tags': tags, 'status': status, 'chapters': chapters, 'url': url
    }

def format_card(info):
    tags_str = ' · '.join(info['tags']) if info['tags'] else '無標籤'
    return (
        f"📖 <b>《{info['title']}》</b>\n"
        f"👤 {info['author']}\n"
        f"🏷️ {tags_str}\n"
        f"📊 {info['status']} · {info['chapters']} 章\n\n"
        f"📝 {info['intro']}"
    )


# ── 下載 ──────────────────────────────────────────────────────

def download_novel(chat_id, url, title):
    key = f"{chat_id}_{title}"
    download_status[key] = {'title': title, 'current': 0, 'total': 0, 'done': False, 'failed': 0}

    send(chat_id, f"⏳ 開始下載《{title}》\n完成後傳 TXT 檔，每 500 章回報進度\n輸入 <code>/status</code> 可查看進度")
    try:
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
            if href and text and '付費' not in text:
                ch_url = 'https:' + href if href.startswith('//') else 'https://czbooks.net' + href
                chapters.append({'title': text, 'url': ch_url})

        total = len(chapters)
        download_status[key]['total'] = total

        os.makedirs(os.path.expanduser("~/novels"), exist_ok=True)
        safe = re.sub(r'[^\w\u4e00-\u9fff]+', '_', title)
        out = os.path.expanduser(f"~/novels/{safe}.txt")

        with open(out, 'w', encoding='utf-8') as f:
            f.write(f"《{title}》\n{'='*40}\n\n")

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
                    (content if content else '[抓取失敗]'))
            if not content:
                failed += 1

            download_status[key]['current'] = i + 1
            download_status[key]['failed'] = failed

            if (i + 1) % 500 == 0:
                send(chat_id, f"⏳ 《{title}》進度：{i+1}/{total} 章")

            time.sleep(random.uniform(1.5, 2.5))

        browser.close()
        p.stop()

        download_status[key]['done'] = True
        size_kb = os.path.getsize(out) // 1024
        caption = f"✅ 《{title}》下載完成\n共 {total} 章 · {size_kb} KB"
        if failed:
            caption += f"\n⚠️ {failed} 章抓取失敗"
        send_file(chat_id, out, caption)
        download_status.pop(key, None)

    except Exception as e:
        download_status[key]['done'] = True
        send(chat_id, f"❌ 下載失敗：{e}")
        download_status.pop(key, None)


# ── Inline Keyboard ───────────────────────────────────────────

PAGE_SIZE = 8

def make_list_keyboard(results, page=0):
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(results))
    page_results = results[start:end]
    total_pages = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE

    buttons = []
    for i, r in enumerate(page_results):
        tag = '✅' if r['done'] else '🔄'
        label = f"{tag} {r['title'][:22]}"
        buttons.append([{'text': label, 'callback_data': f"book_{start+i}"}])

    # 翻頁按鈕
    nav = []
    if page > 0:
        nav.append({'text': '⬅️ 上一頁', 'callback_data': f"page_{page-1}"})
    if end < len(results):
        nav.append({'text': '下一頁 ➡️', 'callback_data': f"page_{page+1}"})
    if nav:
        buttons.append(nav)

    if total_pages > 1:
        buttons.append([{'text': f'第 {page+1}/{total_pages} 頁', 'callback_data': 'noop'}])

    buttons.append([{'text': '❌ 取消', 'callback_data': 'cancel'}])
    return {'inline_keyboard': buttons}

def make_confirm_keyboard():
    return {'inline_keyboard': [
        [{'text': '📥 確認下載', 'callback_data': 'confirm_download'}],
        [{'text': '🔙 返回', 'callback_data': 'back'}, {'text': '❌ 取消', 'callback_data': 'cancel'}]
    ]}

def make_main_keyboard():
    return {'keyboard': [
        ['🔥 熱門榜', '✅ 完本熱門'],
        ['玄幻', '武俠', '歷史'],
        ['科幻', '靈異', '都市'],
        ['/status', '/cancel'],
    ], 'resize_keyboard': True}


# ── 顯示結果 ──────────────────────────────────────────────────

def show_results(chat_id, results, title_text, page=0):
    if not results:
        send(chat_id, "❌ 找不到結果，試試不同關鍵字")
        return
    total = len(results)
    msg = f"{title_text}（共 {total} 本，已過濾言情/耽美）\n點選書名查看詳情："
    keyboard = make_list_keyboard(results, page)
    send(chat_id, msg, reply_markup=keyboard)
    user_state[chat_id] = {'action': 'select', 'results': results, 'page': page, 'title': title_text}


# ── 訊息處理 ──────────────────────────────────────────────────

def handle_message(msg):
    chat_id = str(msg['chat']['id'])
    text = msg.get('text', '').strip()
    if not text:
        return
    if chat_id != TONY_ID:
        send(chat_id, "⛔ 私人機器人")
        return

    if text in ['/start', '/help']:
        send(chat_id,
            "📚 <b>小說下載機器人</b>\n\n"
            "• 直接輸入書名 → 搜尋\n"
            "• 點下方按鈕快速選分類\n"
            "• <code>/status</code> → 查看下載進度\n"
            "• <code>/cancel</code> → 取消目前操作",
            reply_markup=make_main_keyboard())
        return

    if text == '/cancel':
        user_state.pop(chat_id, None)
        send(chat_id, "✅ 已取消", reply_markup=make_main_keyboard())
        return

    if text == '/status':
        active = {k: v for k, v in download_status.items() if k.startswith(chat_id)}
        if not active:
            send(chat_id, "📭 目前沒有進行中的下載")
        else:
            msg = "📊 <b>下載進度</b>\n\n"
            for k, s in active.items():
                pct = f"{s['current']}/{s['total']}" if s['total'] else '準備中'
                msg += f"📖 《{s['title']}》\n進度：{pct} 章\n"
                if s['failed']:
                    msg += f"⚠️ {s['failed']} 章失敗\n"
            send(chat_id, msg)
        return

    if text == '🔥 熱門榜':
        send(chat_id, "⏳ 取得熱門榜...")
        threading.Thread(target=lambda: show_results(
            chat_id, get_hot_list(limit=20), "🔥 熱門榜"), daemon=True).start()
        return

    if text == '✅ 完本熱門':
        send(chat_id, "⏳ 搜尋完本小說...")
        threading.Thread(target=lambda: show_results(
            chat_id, search_complete(limit=20), "✅ 完本小說"), daemon=True).start()
        return

    if text in CATEGORIES:
        cat = text
        send(chat_id, f"⏳ 取得「{cat}」分類熱門...")
        threading.Thread(target=lambda: show_results(
            chat_id, get_hot_list(cat, limit=20), f"🔥 {cat} 熱門"), daemon=True).start()
        return

    # 關鍵字搜尋
    send(chat_id, f"🔍 搜尋「{text}」中...")
    threading.Thread(target=lambda: show_results(
        chat_id, search_novels(text, limit=20), f"📚 「{text}」搜尋結果"), daemon=True).start()


def handle_callback(cb):
    chat_id = str(cb['message']['chat']['id'])
    message_id = cb['message']['message_id']
    data = cb.get('data', '')
    cb_id = cb['id']

    if chat_id != TONY_ID:
        answer_callback(cb_id, "⛔ 私人機器人")
        return

    answer_callback(cb_id)

    if data == 'noop':
        return

    if data == 'cancel':
        user_state.pop(chat_id, None)
        edit_message(chat_id, message_id, "✅ 已取消")
        return

    state = user_state.get(chat_id, {})

    # 翻頁
    if data.startswith('page_') and state.get('action') == 'select':
        page = int(data.split('_')[1])
        results = state.get('results', [])
        title_text = state.get('title', '搜尋結果')
        total = len(results)
        msg = f"{title_text}（共 {total} 本，已過濾言情/耽美）\n點選書名查看詳情："
        keyboard = make_list_keyboard(results, page)
        edit_message(chat_id, message_id, msg, reply_markup=keyboard)
        user_state[chat_id]['page'] = page
        return

    # 選書
    if data.startswith('book_') and state.get('action') == 'select':
        idx = int(data.split('_')[1])
        results = state.get('results', [])
        if 0 <= idx < len(results):
            book = results[idx]
            user_state[chat_id] = {'action': 'confirm', 'book': book}
            edit_message(chat_id, message_id, f"⏳ 讀取《{book['title']}》詳情...")
            def load_detail():
                try:
                    html = get_html(book['url'])
                    info = parse_book_info(html, book['url'])
                    card = format_card(info)
                    user_state[chat_id] = {'action': 'confirm', 'book': book}
                    edit_message(chat_id, message_id, card,
                        reply_markup=make_confirm_keyboard())
                except Exception as e:
                    edit_message(chat_id, message_id, f"❌ 讀取失敗：{e}")
            threading.Thread(target=load_detail, daemon=True).start()
        return

    # 確認下載
    if data == 'confirm_download' and state.get('action') == 'confirm':
        book = state.get('book', {})
        user_state.pop(chat_id, None)
        edit_message(chat_id, message_id,
            f"📥 已加入下載佇列\n《{book['title']}》\n\n輸入 /status 查看進度")
        threading.Thread(target=download_novel,
            args=(chat_id, book['url'], book['title']), daemon=True).start()
        return

    if data == 'back':
        user_state.pop(chat_id, None)
        edit_message(chat_id, message_id, "已返回，請重新搜尋或選分類")


# ── 主迴圈 ────────────────────────────────────────────────────

def run():
    print("🤖 小說機器人 v2 啟動")
    offset = 0
    while True:
        try:
            r = requests.get(f"{API}/getUpdates",
                params={'offset': offset, 'timeout': 30}, timeout=35)
            for u in r.json().get('result', []):
                offset = u['update_id'] + 1
                if 'message' in u:
                    threading.Thread(target=handle_message,
                        args=(u['message'],), daemon=True).start()
                elif 'callback_query' in u:
                    threading.Thread(target=handle_callback,
                        args=(u['callback_query'],), daemon=True).start()
        except Exception as e:
            print(f"錯誤：{e}")
            time.sleep(5)

if __name__ == '__main__':
    run()
