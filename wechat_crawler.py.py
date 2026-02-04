import requests
import json
import time
import os
import re

# 配置和数据文件路径
CONFIG_FILE = "config.json"
FAKEID_FILE = "gzh.txt"
ACCOUNT_NAMES_FILE = "公众号名字"
HISTORY_FILE = "history.json"
OUTPUT_FILE = "wx_poc.txt"
ARTICLES_BASE_DIR = "公众号文章"

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filepath, data):
    # 保存 JSON 时保留中文
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_fakeids():
    if not os.path.exists(FAKEID_FILE):
        return []
    with open(FAKEID_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_account_names():
    if not os.path.exists(ACCOUNT_NAMES_FILE):
        return {}
    with open(ACCOUNT_NAMES_FILE, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    return {i: name for i, name in enumerate(names)}

def get_headers(cookie, token):
    return {
        "Host": "mp.weixin.qq.com",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
        "Cookie": cookie,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&token={token}&lang=zh_CN",
        "Origin": "https://mp.weixin.qq.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

def get_articles(fakeid, token, cookie, begin=0, count=5):
    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    headers = get_headers(cookie, token)
    
    params = {
        "sub": "list",
        "begin": str(begin),
        "count": str(count),
        "fakeid": fakeid,
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "base_resp" in data and data["base_resp"]["ret"] != 0:
            print(f"API Error: {data['base_resp']}")
            return [], 0, None
        
        # publish_page 是一个 JSON 字符串，需要再次解析
        if "publish_page" in data:
            publish_page = json.loads(data["publish_page"])
            publish_list = publish_page.get("publish_list", [])
            total_count = publish_page.get("total_count", 0)
            
            # 从 publish_list 中提取所有文章
            articles = []
            for publish_item in publish_list:
                publish_info = json.loads(publish_item.get("publish_info", "{}"))
                appmsg_info = publish_info.get("appmsg_info", [])
                for appmsg in appmsg_info:
                    articles.append({
                        "title": appmsg.get("title"),
                        "link": appmsg.get("content_url"),
                        "create_time": publish_info.get("sent_info", {}).get("time", 0),
                        "digest": appmsg.get("digest", ""),
                        "author": appmsg.get("author", "")
                    })
            
            return articles, total_count, None
        else:
            print("未找到 publish_page 字段")
            return [], 0, None
            
    except Exception as e:
        print(f"请求失败: {e}")
        return [], 0, None

def is_valid_article_link(link):
    """
    判断文章链接是否有效
    包含 tempkey= 的链接说明文章已删除或失效
    """
    if not link:
        return False
    # 检查是否包含 tempkey= 参数（说明文章已失效）
    if 'tempkey=' in link:
        return False
    return True

def clean_filename(title):
    # 去除非法字符
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def html_to_markdown(html):
    """
    Simple Regex-based HTML to Markdown converter.
    """
    # Remove style and script
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
    
    # Extract images: <img ... data-src="..."> or <img ... src="...">
    # Do this BEFORE removing any tags
    def replace_img(match):
        src = match.group(1) or match.group(2)
        return f"\n![]({src})\n"
    
    # Replace img tags with markdown images
    html = re.sub(r'<img[^>]+data-src="([^"]+)"[^>]*>', replace_img, html)
    html = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', replace_img, html)
    
    # Handle code blocks - <pre><code>...</code></pre> or <pre>...</pre>
    def replace_pre_code(match):
        code_content = match.group(1)
        # Remove inner <code> tags if present
        code_content = re.sub(r'<code[^>]*>(.*?)</code>', r'\1', code_content, flags=re.DOTALL)
        # Decode HTML entities in code
        code_content = code_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
        code_content = code_content.replace('&nbsp;', ' ')
        return f"\n```\n{code_content}\n```\n"
    
    html = re.sub(r'<pre[^>]*>(.*?)</pre>', replace_pre_code, html, flags=re.DOTALL)
    
    # Handle inline code - <code>...</code>
    html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL)
    
    # Remove lines that only contain HTML attributes (common in WeChat articles)
    html = re.sub(r'^\s*(class|data-|style|width|height|type|from|wx_fmt|data-ratio|data-type|data-w|data-imgfileid|data-aistatus|data-s)=[^>]*>\s*$', '', html, flags=re.MULTILINE)
    
    # Headers
    for i in range(6, 0, -1):
        html = re.sub(f'<h{i}[^>]*>(.*?)</h{i}>', '#' * i + r' \1\n', html)
        
    # Paragraphs and Breaks
    html = re.sub(r'<p[^>]*>', '\n', html)
    html = re.sub(r'</p>', '\n', html)
    html = re.sub(r'<br\s*/?>', '\n', html)
    
    # Bold/Strong
    html = re.sub(r'<(b|strong)[^>]*>(.*?)</\1>', r'**\2**', html)
    
    # Lists (Simple)
    html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html)
    
    # Remove all remaining tags (including self-closing)
    html = re.sub(r'<[^>]+>', '', html)
    
    # Decode entities (basic)
    html = html.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
    
    # Collapse multiple newlines and spaces
    html = re.sub(r'\n{3,}', '\n\n', html)
    html = re.sub(r' +', ' ', html)
    
    return html.strip()

def save_url_to_md(article, headers, account_name=None):
    url = article.get("link")
    title = article.get("title")
    digest = article.get("digest", "")
    
    # Try to find date - create_time is timestamp
    try:
        create_time = article.get("create_time")
        date_str = time.strftime("%Y-%m-%d", time.localtime(create_time))
    except:
        date_str = "Unknown"

    if not url:
        return

    try:
        # Fetch article content
        resp = requests.get(url, headers=headers)
        resp.encoding = "utf-8"
        content_html = resp.text
        
        # Use provided account name or try to extract from HTML
        folder_name = account_name if account_name else "Unknown_Account"
        
        if folder_name == "Unknown_Account":
            # Try to extract from HTML var nickname
            nick_match = re.search(r'var nickname = "([^"]+)"', content_html)
            if nick_match:
                folder_name = nick_match.group(1)
            elif "profile_meta_nickname" in content_html:
                nick_match_2 = re.search(r'class="profile_meta_value">([^<]+)<', content_html)
                if nick_match_2:
                    folder_name = nick_match_2.group(1).strip()

        # Create base directory if not exists
        if not os.path.exists(ARTICLES_BASE_DIR):
            os.makedirs(ARTICLES_BASE_DIR)
        
        # Create account subdirectory
        safe_account_folder = clean_filename(folder_name)
        account_dir = os.path.join(ARTICLES_BASE_DIR, safe_account_folder)
        if not os.path.exists(account_dir):
            os.makedirs(account_dir)
            
        safe_title = clean_filename(title)
        filename = os.path.join(account_dir, f"{date_str}_{safe_title}.md")
        
        if os.path.exists(filename):
            print(f"  [Jump] File exists: {filename}")
            return

        # Convert to Markdown
        # Only extract the main content container: id="js_content"
        main_content = ""
        content_match = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', content_html, re.DOTALL)
        
        if content_match:
             main_content = content_match.group(1)
        else:
             # Fallback: parsing might be complex, use whole response body
             main_content = re.search(r'<body[^>]*>(.*?)</body>', content_html, re.DOTALL).group(1) if re.search(r'<body', content_html) else content_html

        markdown_content = f"# {title}\n\n"
        markdown_content += f"**Date:** {date_str}\n"
        markdown_content += f"**Link:** {url}\n"
        markdown_content += f"**Account:** {folder_name}\n"
        if digest:
            markdown_content += f"**Summary:** {digest}\n"
        markdown_content += "\n"
        markdown_content += html_to_markdown(main_content)
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        # Check file size and delete if too small
        config = load_json(CONFIG_FILE)
        min_file_size_kb = config.get("min_file_size_kb", 3)
        min_file_size_bytes = min_file_size_kb * 1024
        
        file_size = os.path.getsize(filename)
        if file_size < min_file_size_bytes:
            print(f"  [Delete] File too small ({file_size} bytes): {filename}")
            os.remove(filename)
        else:
            print(f"  [Saved] {filename} ({file_size} bytes)")
        
        time.sleep(1)

    except Exception as e:
        print(f"  [Error] Failed to save {title}: {e}")

def load_account_latest_articles():
    """
    从 wx_poc.txt 中读取每个公众号的最新文章链接
    返回字典: {公众号名称: 最新文章链接}
    """
    account_latest = {}
    if not os.path.exists(OUTPUT_FILE):
        return account_latest
    
    current_account = None
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("文章名字："):
                # 提取公众号名称（从文件名中）
                title = line.replace("文章名字：", "")
                # 尝试从文件名中提取公众号名
                # 格式类似: 公众号文章/公众号名/日期_标题.md
                # 但这里只有标题，无法直接获取
                # 我们需要另一种方式
                pass
            elif line.startswith("文章链接："):
                link = line.replace("文章链接：", "")
                if current_account:
                    account_latest[current_account] = link
                    current_account = None
    
    return account_latest

def load_account_first_article_from_txt():
    """
    从 wx_poc.txt 中读取每个公众号的第一篇文章链接
    返回字典: {公众号名称: 第一篇文章链接}
    """
    account_first_articles = {}
    if not os.path.exists(OUTPUT_FILE):
        return account_first_articles
    
    current_account = None
    first_article_link = None
    
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("公众号："):
                current_account = line.replace("公众号：", "")
                first_article_link = None
            elif line.startswith("第一篇文章链接：") and current_account:
                first_article_link = line.replace("第一篇文章链接：", "")
                account_first_articles[current_account] = first_article_link
    
    return account_first_articles
def mode_archive(fakeids, token, cookie, account_names):
    """存档模式：爬取所有文章"""
    print("--- 启动存档模式 ---")
    headers = get_headers(cookie, token)
    
    # Load existing links from wx_poc.txt to avoid duplicates
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("文章链接："):
                    link = line.strip().replace("文章链接：", "")
                    existing_links.add(link)
    
    # Load first articles from wx_poc.txt for comparison
    account_first_articles = load_account_first_article_from_txt()
    print(f"已加载 {len(account_first_articles)} 个公众号的第一篇文章记录")
    
    # Create base directory if not exists
    if not os.path.exists(ARTICLES_BASE_DIR):
        os.makedirs(ARTICLES_BASE_DIR)
    
    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, "Unknown_Account")
        print(f"正在处理 fakeid: {fakeid} ({account_name})")
        
        # Get first article to check if already archived
        articles_first, _, _ = get_articles(fakeid, token, cookie, 0, 1)
        if articles_first:
            first_article_link = articles_first[0].get('link')
            
            # Check if this account has archived articles in wx_poc.txt
            if account_name in account_first_articles:
                archived_first_link = account_first_articles[account_name]
                if first_article_link == archived_first_link:
                    print(f"  [Skip] 公众号第一篇文章已存档，跳过: {account_name}")
                    continue
                else:
                    print(f"  [New] 发现新内容，开始爬取: {account_name}")
            else:
                print(f"  [New] 首次爬取，开始处理: {account_name}")
        
        begin = 0
        count = 10
        should_stop = False
        account_articles = []
        
        while not should_stop:
            articles, total, _ = get_articles(fakeid, token, cookie, begin, count)
            if not articles:
                print(f"  没有更多文章或获取失败")
                break
                
            print(f"  获取到 {len(articles)} 篇文章 (当前进度: {begin})")
            
            for article in articles:
                link = article.get('link')
                # Check if this article is already archived in wx_poc.txt
                if account_name in account_first_articles:
                    if link == account_first_articles[account_name]:
                        print(f"  [Stop] 找到已存档文章，停止爬取: {article.get('title')}")
                        should_stop = True
                        break
                # Skip invalid articles (deleted or expired)
                if not is_valid_article_link(link):
                    print(f"  [Skip] 文章已失效，跳过: {article.get('title')}")
                    continue
                # Only collect if not already archived
                if link not in existing_links:
                    account_articles.append(article)
            
            if should_stop:
                break
                
            if len(articles) < count:
                print("  已到达最后一页")
                break
                
            begin += count
            time.sleep(3)
        
        # Save to txt with account header
        if account_articles:
            # Filter out invalid articles before saving
            valid_articles = [a for a in account_articles if is_valid_article_link(a.get('link'))]
            
            if valid_articles:
                with open(OUTPUT_FILE, "a+", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write(f"公众号：{account_name}\n")
                    f.write(f"文章数量：{len(valid_articles)}篇\n")
                    f.write(f"第一篇文章：{valid_articles[0].get('title')}\n")
                    f.write(f"第一篇文章链接：{valid_articles[0].get('link')}\n")
                    f.write("=" * 60 + "\n")
                    for article in valid_articles:
                        f.write(f"文章名字：{article.get('title')}\n")
                        f.write(f"文章链接：{article.get('link')}\n")
                        f.write("-" * 50 + "\n")
                        existing_links.add(article.get('link'))
                
                # Save to Markdown (only valid articles)
                for article in valid_articles:
                    save_url_to_md(article, headers, account_name)

def mode_update(fakeids, token, cookie, history, account_names):
    """更新模式：增量爬取"""
    print("--- 启动更新模式 ---")
    headers = get_headers(cookie, token)
    
    # Load existing links to avoid duplicates
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("文章链接："):
                    link = line.strip().replace("文章链接：", "")
                    existing_links.add(link)
    
    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, "Unknown_Account")
        print(f"正在检查 fakeid: {fakeid} ({account_name})")
        
        last_article_info = history.get(fakeid, {})
        last_title = last_article_info.get("last_article_title")
        
        begin = 0
        count = 10
        new_articles = []
        found_overlap = False
        
        while not found_overlap:
            articles, total, _ = get_articles(fakeid, token, cookie, begin, count)
            if not articles:
                break
                
            for article in articles:
                title = article.get("title")
                link = article.get('link')
                
                if title == last_title:
                    print(f"  找到上次最后更新的文章: {title}，停止本号更新")
                    found_overlap = True
                    break
                
                # Skip invalid articles (deleted or expired)
                if not is_valid_article_link(link):
                    print(f"  [Skip] 文章已失效，跳过: {title}")
                    continue
                
                new_articles.append(article)
            
            if len(articles) < count or found_overlap:
                break
                
            begin += count
            time.sleep(3)
            
        if new_articles:
            # Filter out invalid articles
            valid_articles = [a for a in new_articles if is_valid_article_link(a.get('link'))]
            
            if valid_articles:
                print(f"  发现 {len(valid_articles)} 篇新文章")
                
                # Save to txt log with account header (new format)
                with open(OUTPUT_FILE, "a+", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write(f"公众号：{account_name}\n")
                    f.write(f"文章数量：{len(valid_articles)}篇\n")
                    f.write(f"第一篇文章：{valid_articles[0].get('title')}\n")
                    f.write(f"第一篇文章链接：{valid_articles[0].get('link')}\n")
                    f.write("=" * 60 + "\n")
                    for article in valid_articles:
                        f.write(f"文章名字：{article.get('title')}\n")
                        f.write(f"文章链接：{article.get('link')}\n")
                        f.write("-" * 50 + "\n")
                        existing_links.add(article.get('link'))
                
                # Process new articles (Save to MD)
                for article in valid_articles:
                    save_url_to_md(article, headers, account_name)
                
                # Update history with the NEWEST article
                newest = valid_articles[0]
                history[fakeid] = {
                    "last_article_title": newest.get("title"),
                    "last_article_url": newest.get("link")
                }
            else:
                print("  发现的新文章均已失效")
        else:
            print("  无新文章")

    save_json(HISTORY_FILE, history)

def main():
    config = load_json(CONFIG_FILE)
    token = config.get("token")
    cookie = config.get("cookie")
    
    if not token or not cookie:
        print("错误: config.json 中缺少 token 或 cookie")
        return

    fakeids = load_fakeids()
    if not fakeids:
        print("错误: gzh.txt 为空或不存在")
        return
    print(f"加载了 {len(fakeids)} 个公众号")

    account_names = load_account_names()
    print(f"加载了 {len(account_names)} 个公众号名称")

    # 持续监控模式
    config = load_json(CONFIG_FILE)
    check_interval_minutes = config.get("check_interval_minutes", 60)
    check_interval_seconds = check_interval_minutes * 60
    
    print("启动持续监控模式...")
    print(f"每{check_interval_minutes}分钟检查一次公众号更新\n")
    
    while True:
        try:
            print(f"\n{'='*60}")
            print(f"开始检查更新 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}\n")
            
            # 运行监控检查
            mode_archive(fakeids, token, cookie, account_names)
            
            print(f"\n{'='*60}")
            print(f"检查完成 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            next_check_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + check_interval_seconds))
            print(f"下次检查时间: {next_check_time}")
            print(f"{'='*60}\n")
            
            # 等待指定时间
            print(f"等待{check_interval_minutes}分钟后进行下一次检查...")
            time.sleep(check_interval_seconds)
            
        except KeyboardInterrupt:
            print("\n\n监控已停止")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            retry_interval_minutes = config.get("retry_interval_minutes", 5)
            print(f"{retry_interval_minutes}分钟后重试...")
            time.sleep(retry_interval_minutes * 60)

if __name__ == "__main__":
    main()