"""
Twitter 爬虫工具 v3
支持图片下载、PDF生成、GitHub上传
"""
import asyncio
import base64
import json
import os
import random
import time
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from dataclasses import dataclass, asdict


@dataclass
class Tweet:
    """推文数据结构"""
    tweet_id: str
    content: str
    author: str
    author_handle: str
    created_at: str
    likes: int
    retweets: int
    replies: int
    url: str
    images: List[str] = None  # 图片URL列表
    is_retweet: bool = False
    original_author: Optional[str] = None
    scraped_at: str = ""


class TwitterScraper:
    """
    Twitter 爬虫工具 v3
    """
    
    def __init__(self, headless: bool = False, slow_mo: int = 100):
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        
        # 防封策略
        self.min_delay = 2
        self.max_delay = 5
        
        # 目录
        self.output_dir = Path("assets/twitter_data")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.output_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    async def init_browser(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        
        self.context = await playwright.chromium.launch_persistent_context(
            user_data_dir="./twitter_user_data",
            headless=self.headless,
            slow_mo=self.slow_mo,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        print("✅ 浏览器初始化成功")
    
    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        print("✅ 浏览器已关闭")
    
    def _random_delay(self):
        """随机延时"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"⏱️  等待 {delay:.1f} 秒...")
        time.sleep(delay)
    
    async def login(self, username: str = None, password: str = None, cookies_path: str = None):
        """登录"""
        print("🔐 开始登录 Twitter...")
        
        if cookies_path and os.path.exists(cookies_path):
            print("📂 加载 cookies...")
            with open(cookies_path, 'r') as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            await self.page.goto("https://twitter.com/home")
            await asyncio.sleep(3)
            
            if "login" not in self.page.url:
                print("✅ 已登录")
                self.is_logged_in = True
                return True
        
        await self.page.goto("https://twitter.com/login")
        await asyncio.sleep(2)
        
        if username and password:
            print("📝 使用账号密码登录...")
            await self._login_with_credentials(username, password)
        else:
            print("⚠️  请在浏览器中登录，完成后按 Enter...")
            input()
        
        await self.page.goto("https://twitter.com/home")
        await asyncio.sleep(3)
        
        if "login" not in self.page.url:
            print("✅ 登录成功！")
            self.is_logged_in = True
            if cookies_path:
                await self._save_cookies(cookies_path)
        else:
            print("❌ 登录失败")
        
        return self.is_logged_in
    
    async def _login_with_credentials(self, username: str, password: str):
        await asyncio.sleep(2)
        await self.page.fill('input[autocomplete="username"]', username)
        await asyncio.sleep(1)
        
        next_btn = self.page.locator('button:has-text("下一步"), button:has-text("Next")')
        if await next_btn.is_visible():
            await next_btn.click()
            await asyncio.sleep(2)
        
        await self.page.fill('input[name="password"]', password)
        await asyncio.sleep(1)
        
        login_btn = self.page.locator('button:has-text("登录"), button:has-text("Log in")')
        await login_btn.click()
        await asyncio.sleep(3)
    
    async def _save_cookies(self, path: str):
        cookies = await self.context.cookies()
        with open(path, 'w') as f:
            json.dump(cookies, f)
        print(f"💾 Cookies 已保存")
    
    async def scrape_profile_tweets(self, username: str, max_count: int = 50, download_images: bool = True) -> List[Tweet]:
        """爬取用户发帖（支持下载图片）"""
        print(f"📥 开始爬取 @{username} 的发帖...")
        print(f"📸 图片下载: {'开启' if download_images else '关闭'}")
        
        tweets = []
        url = f"https://twitter.com/{username}"
        await self.page.goto(url)
        await asyncio.sleep(3)
        
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            print(f"📜 滚动第 {scroll_count + 1} 次...")
            
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            new_tweets = await self._parse_tweets_from_page(download_images)
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ {len(tweets)}. {tweet.content[:40]}...")
                    if tweet.images:
                        print(f"     📸 含 {len(tweet.images)} 张图片")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条发帖")
        return tweets[:max_count]
    
    async def scrape_retweets(self, username: str, max_count: int = 50) -> List[Tweet]:
        """爬取转推"""
        print(f"📥 开始爬取转推...")
        
        tweets = []
        await self.page.goto(f"https://twitter.com/{username}")
        await asyncio.sleep(3)
        
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            new_tweets = await self._parse_tweets_from_page(False)
            for tweet in new_tweets:
                if tweet not in tweets and tweet.is_retweet:
                    tweets.append(tweet)
                    print(f"  ✅ {len(tweets)}. 转推: {tweet.content[:40]}...")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条转推")
        return tweets[:max_count]
    
    async def scrape_bookmarks(self, max_count: int = 50, download_images: bool = True) -> List[Tweet]:
        """爬取书签"""
        if not self.is_logged_in:
            print("❌ 需要登录")
            return []
        
        print(f"📥 开始爬取书签...")
        
        tweets = []
        await self.page.goto("https://twitter.com/i/bookmarks")
        await asyncio.sleep(3)
        
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            new_tweets = await self._parse_tweets_from_page(download_images)
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ {len(tweets)}. {tweet.content[:40]}...")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条书签")
        return tweets[:max_count]
    
    async def _parse_tweets_from_page(self, download_images: bool = True) -> List[Tweet]:
        """解析推文"""
        tweets = []
        
        try:
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=5000)
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')
            
            for element in tweet_elements:
                try:
                    tweet = await self._parse_tweet_element(element, download_images)
                    if tweet:
                        tweets.append(tweet)
                except:
                    continue
        
        except Exception as e:
            print(f"⚠️  解析出错: {e}")
        
        return tweets
    
    async def _parse_tweet_element(self, element, download_images: bool = True) -> Optional[Tweet]:
        """解析单个推文"""
        try:
            # 内容
            content_elem = await element.query_selector('[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""
            
            # 作者
            author_elem = await element.query_selector('[data-testid="User-Name"]')
            if author_elem:
                author_text = await author_elem.inner_text()
                lines = author_text.split('\n')
                author = lines[0] if lines else "Unknown"
                author_handle = lines[1] if len(lines) > 1 else "Unknown"
            else:
                author = "Unknown"
                author_handle = "Unknown"
            
            # 时间
            time_elem = await element.query_selector('time')
            created_at = await time_elem.get_attribute('datetime') if time_elem else ""
            
            # 互动数据
            likes = await self._get_interaction_count(element, 'Like')
            retweets = await self._get_interaction_count(element, 'Retweet')
            replies = await self._get_interaction_count(element, 'Reply')
            
            # 链接
            link_elem = await element.query_selector('a[href*="/status/"]')
            url = await link_elem.get_attribute('href') if link_elem else ""
            tweet_id = url.split('/')[-1] if url else ""
            full_url = f"https://twitter.com{url}" if url and not url.startswith('http') else url
            
            # 图片
            images = []
            if download_images:
                images = await self._extract_images(element, tweet_id)
            
            # 转推标记
            retweet_indicator = await element.query_selector('[data-testid="socialContext"]')
            is_retweet = False
            original_author = None
            if retweet_indicator:
                retweet_text = await retweet_indicator.inner_text()
                if "转推" in retweet_text or "Retweeted" in retweet_text:
                    is_retweet = True
                    original_author = retweet_text.replace("转推", "").replace("Retweeted", "").strip()
            
            return Tweet(
                tweet_id=tweet_id,
                content=content,
                author=author,
                author_handle=author_handle,
                created_at=created_at,
                likes=likes,
                retweets=retweets,
                replies=replies,
                url=full_url,
                images=images,
                is_retweet=is_retweet,
                original_author=original_author,
                scraped_at=datetime.now().isoformat()
            )
        
        except:
            return None
    
    async def _extract_images(self, element, tweet_id: str) -> List[str]:
        """提取图片"""
        images = []
        try:
            # 查找图片元素
            img_elements = await element.query_selector_all('img[src*="media"]')
            
            for i, img in enumerate(img_elements):
                src = await img.get_attribute('src')
                if src and 'profile' not in src:
                    # 下载图片
                    local_path = await self._download_image(src, tweet_id, i)
                    if local_path:
                        images.append(local_path)
                    self._random_delay()
        except:
            pass
        return images
    
    async def _download_image(self, url: str, tweet_id: str, index: int) -> Optional[str]:
        """下载图片"""
        try:
            # 清理 URL，获取高清图
            url = url.replace('&name=small', '&name=large').replace('&name=medium', '&name=large')
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                ext = 'jpg' if 'jpg' in response.headers.get('content-type', '') else 'png'
                filename = f"{tweet_id}_{index}.{ext}"
                filepath = self.images_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                print(f"     📥 下载图片: {filename}")
                return str(filepath)
        except Exception as e:
            print(f"     ⚠️  下载失败: {e}")
        return None
    
    async def _get_interaction_count(self, element, interaction_type: str) -> int:
        """获取互动数"""
        try:
            selector = f'button:has-text("{interaction_type}") >> span'
            count_elem = await element.query_selector(selector)
            if count_elem:
                count_text = await count_elem.inner_text()
                return self._parse_count(count_text)
        except:
            pass
        return 0
    
    def _parse_count(self, text: str) -> int:
        """解析数字"""
        if not text or text.strip() == "":
            return 0
        text = text.strip().replace(',', '')
        if 'K' in text:
            return int(float(text.replace('K', '')) * 1000)
        elif 'M' in text:
            return int(float(text.replace('M', '')) * 1000000)
        try:
            return int(text)
        except:
            return 0
    
    async def save_to_json(self, tweets: List[Tweet], filename: str):
        """保存JSON"""
        output_path = self.output_dir / filename
        data = []
        for tweet in tweets:
            t = asdict(tweet)
            # 图片路径转相对路径
            t['images'] = [str(Path(p).name) for p in tweet.images] if tweet.images else []
            data.append(t)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 已保存: {output_path}")
        return str(output_path)
    
    async def save_to_csv(self, tweets: List[Tweet], filename: str):
        """保存CSV"""
        output_path = self.output_dir / filename
        data = []
        for tweet in tweets:
            t = asdict(tweet)
            t['images'] = ', '.join([Path(p).name for p in tweet.images]) if tweet.images else ''
            data.append(t)
        
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"💾 已保存: {output_path}")
        return str(output_path)
    
    def generate_pdf(self, tweets: List[Tweet], username: str, title: str = "Twitter 推文") -> str:
        """生成 PDF 报告"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
            from reportlab.lib import colors
        except ImportError:
            print("⚠️  需要安装 reportlab: pip install reportlab")
            return None
        
        print("📄 生成 PDF 报告...")
        
        pdf_path = self.output_dir / f"{username}_report.pdf"
        
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # 标题
        title_style = styles['Title']
        title_style.fontSize = 24
        story.append(Paragraph(f"📘 {title}", title_style))
        story.append(Paragraph(f"@{username}", styles['Normal']))
        story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"共 {len(tweets)} 条推文", styles['Normal']))
        story.append(Spacer(1, 2*cm))
        
        # 每条推文
        for i, tweet in enumerate(tweets):
            # 内容
            content_style = styles['Heading3']
            story.append(Paragraph(f"#{i+1} {tweet.created_at[:10]}", content_style))
            
            # 文字内容
            text = tweet.content[:500] + "..." if len(tweet.content) > 500 else tweet.content
            story.append(Paragraph(text.replace('\n', '<br/>'), styles['Normal']))
            
            # 互动数据
            stats = f"❤️ {tweet.likes} | 🔄 {tweet.retweets} | 💬 {tweet.replies}"
            story.append(Paragraph(stats, styles['Normal']))
            
            # 图片
            if tweet.images:
                story.append(Paragraph(f"📸 附件图片 ({len(tweet.images)}张)", styles['Normal']))
                for img_path in tweet.images[:4]:  # 最多4张
                    try:
                        img = Image(img_path, width=6*cm, height=4*cm)
                        story.append(img)
                    except:
                        pass
            
            # 链接
            story.append(Paragraph(f'<link href="{tweet.url}">{tweet.url}</link>', styles['Normal']))
            story.append(Spacer(1, 1*cm))
            
            # 分页
            if i % 5 == 4:
                story.append(PageBreak())
        
        doc.build(story)
        print(f"✅ PDF 已生成: {pdf_path}")
        return str(pdf_path)
    
    def upload_to_github(self, filepath: str, repo: str, token: str) -> Optional[str]:
        """上传文件到 GitHub"""
        import urllib.request
        
        print(f"📤 上传到 GitHub...")
        
        try:
            with open(filepath, 'rb') as f:
                content = base64.b64encode(f.read()).decode()
            
            filename = Path(filepath).name
            api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
            
            # 检查是否已存在
            req = urllib.request.Request(api_url, headers={
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            })
            
            sha = None
            try:
                with urllib.request.urlopen(req) as resp:
                    sha = json.loads(resp.read()).get('sha')
            except:
                pass
            
            # 上传
            data = json.dumps({
                'message': f'Upload {filename}',
                'content': content
            }).encode()
            
            if sha:
                data = json.dumps({
                    'message': f'Update {filename}',
                    'content': content,
                    'sha': sha
                }).encode()
            
            req = urllib.request.Request(api_url, data=data, headers={
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            })
            
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                url = result.get('content', {}).get('html_url', '')
                print(f"✅ 上传成功: {url}")
                return url
        
        except Exception as e:
            print(f"❌ 上传失败: {e}")
        return None
