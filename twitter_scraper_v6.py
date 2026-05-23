#!/usr/bin/env python3
"""
Twitter 爬虫 v6 - 支持手动指定字体
"""
import asyncio
import base64
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️ reportlab 未安装，PDF 功能不可用")


@dataclass
class Tweet:
    id: str
    content: str
    author: str
    author_handle: str
    created_at: str
    likes: int
    retweets: int
    replies: int
    images: List[str]
    url: str


class TwitterScraper:
    def __init__(self, headless: bool = False, slow_mo: int = 100, font_path: str = None):
        self.headless = headless
        self.slow_mo = slow_mo
        self.font_path = font_path or self._find_chinese_font()
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.is_logged_in = False
        
        if REPORTLAB_AVAILABLE:
            self._register_font()
    
    def _find_chinese_font(self) -> str:
        """查找中文字体"""
        font_paths = [
            # Windows
            "C:\\Windows\\Fonts\\msyh.ttc",
            "C:\\Windows\\Fonts\\simhei.ttf",
            "C:\\Windows\\Fonts\\simsun.ttc",
            # Linux WSL
            "/mnt/c/Windows/Fonts/msyh.ttc",
            "/mnt/c/Windows/Fonts/simhei.ttf",
            # Linux
            "/usr/share/fonts/truetype/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            # macOS
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        
        for path in font_paths:
            if Path(path).exists():
                print(f"✅ 找到字体: {path}")
                return path
        
        print("⚠️ 未找到中文字体，尝试使用默认字体")
        return ""
    
    def _register_font(self):
        """注册中文字体"""
        if not self.font_path or not Path(self.font_path).exists():
            print("⚠️ 字体文件不存在，跳过字体注册")
            return
        
        try:
            pdfmetrics.registerFont(TTFont('ChineseFont', self.font_path))
            print(f"✅ 字体注册成功: {self.font_path}")
        except Exception as e:
            print(f"⚠️ 字体注册失败: {e}")
    
    async def init_browser(self):
        """初始化浏览器"""
        print("🔧 初始化浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()
        print("✅ 浏览器初始化成功")
    
    async def login(self, username: str = None, password: str = None):
        """登录"""
        print("📝 开始登录...")
        await self.page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        if "login" not in self.page.url.lower():
            print("✅ 已登录")
            self.is_logged_in = True
            return True
        
        print("⚠️ 请在浏览器中登录...")
        print("登录成功后按 Enter 继续...")
        input()
        self.is_logged_in = True
        return True
    
    async def scrape_tweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """爬取用户推文"""
        print(f"📝 开始爬取 {username} 的推文...")
        url = f"https://twitter.com/{username}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        tweets = []
        seen_ids = set()
        
        while len(tweets) < max_count:
            article_selector = 'article[role="article"]'
            articles = await self.page.query_selector_all(article_selector)
            
            for article in articles:
                if len(tweets) >= max_count:
                    break
                
                try:
                    tweet = await self._parse_tweet(article, username)
                    if tweet and tweet.id not in seen_ids:
                        seen_ids.add(tweet.id)
                        tweets.append(tweet)
                        print(f"  📄 爬取 {len(tweets)}/{max_count}: {tweet.content[:50]}...")
                except Exception as e:
                    continue
            
            if len(tweets) >= max_count:
                break
            
            await self.page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(random.uniform(2, 4))
        
        print(f"✅ 完成！共爬取 {len(tweets)} 条推文")
        return tweets
    
    async def _parse_tweet(self, article, username: str) -> Optional[Tweet]:
        """解析单条推文"""
        try:
            # 获取文本内容
            content_elem = await article.query_selector('div[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""
            
            # 获取时间
            time_elem = await article.query_selector('time')
            datetime_str = await time_elem.get_attribute('datetime') if time_elem else ""
            
            # 获取链接
            link_elem = await article.query_selector('a[href*="/status/"]')
            href = await link_elem.get_attribute('href') if link_elem else ""
            tweet_id = re.search(r'/status/(\d+)', href).group(1) if href else ""
            url = f"https://twitter.com{href}" if href else ""
            
            # 获取图片
            img_elems = await article.query_selector_all('img[src*="media"]')
            images = []
            for img in img_elems:
                src = await img.get_attribute('src')
                if src:
                    src = re.sub(r'\?.*', '', src)
                    if 'profile_images' not in src:
                        images.append(src + "&name=orig")
            
            # 交互数据
            likes = retweets = replies = 0
            spans = await article.query_selector_all('span')
            for span in spans:
                text = await span.inner_text()
                if '喜欢' in text or 'likes' in text.lower():
                    try:
                        likes = int(re.sub(r'[^\d]', '', text)) or 0
                    except:
                        pass
                elif '转推' in text or 'Retweet' in text:
                    try:
                        retweets = int(re.sub(r'[^\d]', '', text)) or 0
                    except:
                        pass
            
            return Tweet(
                id=tweet_id,
                content=content,
                author=username,
                author_handle=f"@{username}",
                created_at=datetime_str.replace('T', ' ').replace('Z', '') if datetime_str else "",
                likes=likes,
                retweets=retweets,
                replies=replies,
                images=images,
                url=url
            )
        except Exception as e:
            return None
    
    async def download_images(self, tweets: List[Tweet], output_dir: str = "images"):
        """下载推文图片"""
        Path(output_dir).mkdir(exist_ok=True)
        
        for tweet in tweets:
            for i, img_url in enumerate(tweet.images):
                try:
                    filename = f"{tweet.id}_{i}.jpg"
                    filepath = Path(output_dir) / filename
                    if filepath.exists():
                        continue
                    
                    response = await self.page.request.get(img_url)
                    if response.ok:
                        filepath.write_bytes(await response.body())
                        print(f"  📥 下载图片: {filename}")
                except Exception as e:
                    print(f"  ⚠️ 下载失败: {e}")
                
                await asyncio.sleep(random.uniform(1, 2))
    
    async def save_to_json(self, tweets: List[Tweet], filename: str):
        """保存为 JSON"""
        Path("assets/twitter_data").mkdir(parents=True, exist_ok=True)
        filepath = Path("assets/twitter_data") / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([asdict(t) for t in tweets], f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存 JSON: {filepath}")
    
    async def save_to_csv(self, tweets: List[Tweet], filename: str):
        """保存为 CSV"""
        import csv
        Path("assets/twitter_data").mkdir(parents=True, exist_ok=True)
        filepath = Path("assets/twitter_data") / filename
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', '内容', '作者', '账号', '时间', '点赞', '转发', '回复', '链接'])
            for t in tweets:
                writer.writerow([t.id, t.content, t.author, t.author_handle, t.created_at, t.likes, t.retweets, t.replies, t.url])
        print(f"✅ 已保存 CSV: {filepath}")
    
    async def generate_pdf(self, tweets: List[Tweet], filename: str):
        """生成 PDF 报告"""
        if not REPORTLAB_AVAILABLE:
            print("⚠️ reportlab 未安装，无法生成 PDF")
            return
        
        Path("assets/twitter_data").mkdir(parents=True, exist_ok=True)
        filepath = Path("assets/twitter_data") / filename
        
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        story = []
        style = getSampleStyleSheet()
        
        # 使用中文字体
        if self.font_path and Path(self.font_path).exists():
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', self.font_path))
                style.add(getSampleStyleSheet()['Normal'].clone('ChineseStyle'))
                style['ChineseStyle'].fontName = 'ChineseFont'
                style['ChineseStyle'].fontSize = 10
                text_style = style['ChineseStyle']
            except:
                text_style = style['Normal']
        else:
            text_style = style['Normal']
        
        story.append(Paragraph("Twitter 推文报告", style['Title']))
        story.append(Spacer(1, 0.5*cm))
        
        for i, tweet in enumerate(tweets[:50], 1):
            story.append(Paragraph(f"<b>#{i}</b> - {tweet.created_at}", text_style))
            story.append(Paragraph(f"账号: {tweet.author_handle}", text_style))
            story.append(Paragraph(f"内容: {tweet.content}", text_style))
            story.append(Paragraph(f"❤ {tweet.likes} | 🔄 {tweet.retweets} | 💬 {tweet.replies}", text_style))
            story.append(Paragraph(f"<link href='{tweet.url}'>{tweet.url}</link>", text_style))
            
            # 图片
            for img_idx, img_url in enumerate(tweet.images[:2]):
                img_path = Path("images") / f"{tweet.id}_{img_idx}.jpg"
                if img_path.exists():
                    try:
                        story.append(Image(str(img_path), width=15*cm, height=10*cm))
                    except:
                        pass
            
            story.append(Spacer(1, 0.3*cm))
            
            if i % 5 == 0:
                story.append(PageBreak())
        
        doc.build(story)
        print(f"✅ 已生成 PDF: {filepath}")
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            print("🔒 浏览器已关闭")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Twitter 爬虫')
    parser.add_argument('-u', '--username', required=True, help='Twitter 用户名')
    parser.add_argument('-t', '--type', default='tweets', choices=['tweets', 'retweets', 'all'], help='类型')
    parser.add_argument('-m', '--max', type=int, default=100, help='最大数量')
    parser.add_argument('--pdf', action='store_true', help='生成 PDF')
    parser.add_argument('--images', action='store_true', help='下载图片')
    parser.add_argument('--font', type=str, help='指定字体路径 (如: C:\\Windows\\Fonts\\msyh.ttc)')
    
    args = parser.parse_args()
    
    scraper = TwitterScraper(headless=False, font_path=args.font)
    await scraper.init_browser()
    
    try:
        await scraper.login()
        
        tweets = await scraper.scrape_tweets(args.username, args.max)
        
        if tweets:
            await scraper.save_to_json(tweets, f"{args.username}_tweets.json")
            await scraper.save_to_csv(tweets, f"{args.username}_tweets.csv")
            
            if args.images:
                await scraper.download_images(tweets)
            
            if args.pdf:
                await scraper.generate_pdf(tweets, f"{args.username}_report.pdf")
        
        print("\n🎉 完成！")
        input("\n按 Enter 关闭...")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
