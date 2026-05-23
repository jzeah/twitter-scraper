#!/usr/bin/env python3
"""
Twitter 爬虫 v4 - 高清图片 + 大图PDF
"""
import asyncio
import json
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import sys

import pandas as pd
import requests
from playwright.async_api import async_playwright, Page, Browser

@dataclass
class Tweet:
    """推文数据模型"""
    tweet_id: str = ""
    content: str = ""
    author: str = ""
    author_handle: str = ""
    created_at: str = ""
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    url: str = ""
    images: List[str] = None
    is_retweet: bool = False
    original_author: Optional[str] = None
    scraped_at: str = ""

    def __post_init__(self):
        if self.images is None:
            self.images = []

class TwitterScraperV4:
    """Twitter 爬虫 v4"""

    def __init__(self, headless: bool = False, slow_mo: int = 100):
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.is_logged_in = False
        self.output_dir = Path("assets/twitter_data")
        self.images_dir = Path("assets/twitter_data/images")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.page = await self.browser.new_page(viewport={'width': 1280, 'height': 800})
        print("✅ 浏览器初始化成功")

    async def login(self, username: str = None, password: str = None, cookies_path: str = "twitter_cookies.json"):
        """登录 Twitter"""
        print("📝 开始登录...")
        
        # 尝试加载已保存的 cookies
        if Path(cookies_path).exists():
            print("📂 加载已保存的 cookies...")
            cookies = json.loads(Path(cookies_path).read_text())
            await self.page.context.add_cookies(cookies)
        
        # 检查登录状态
        await self.page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        if "login" not in self.page.url.lower():
            print("✅ 已登录")
            self.is_logged_in = True
            # 保存 cookies
            cookies = await self.page.context.cookies()
            Path(cookies_path).write_text(json.dumps(cookies, indent=2))
            return True

        # 如果需要手动登录
        if not username:
            print("⚠️ 未提供账号密码，请在弹出的浏览器中登录...")
            print("登录成功后按 Enter 继续...")
            input()
            self.is_logged_in = True
            # 保存 cookies
            cookies = await self.page.context.cookies()
            Path(cookies_path).write_text(json.dumps(cookies, indent=2))
            return True

        # 自动登录
        await self._auto_login(username, password)
        self.is_logged_in = True
        return True

    async def _auto_login(self, username: str, password: str):
        """自动登录"""
        await self.page.goto("https://twitter.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        await self.page.fill('input[autocomplete="username"]', username)
        await asyncio.sleep(1)
        await self.page.click('button:has-text("下一步")')
        await asyncio.sleep(2)
        
        await self.page.fill('input[name="password"]', password)
        await asyncio.sleep(1)
        await self.page.click('button:has-text("登录")')
        await asyncio.sleep(5)

    async def scrape_profile_tweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """爬取用户发帖"""
        print(f"📝 爬取 @{username} 的发帖...")
        
        tweets = []
        scroll_count = 0
        max_scrolls = (max_count // 20) + 5
        
        await self.page.goto(f"https://twitter.com/{username}", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        while len(tweets) < max_count and scroll_count < max_scrolls:
            # 滚动加载
            await self.page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(random.uniform(2, 4))
            scroll_count += 1
            
            # 解析推文
            new_tweets = await self._parse_tweets(download_images=True)
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
            
            print(f"   已爬取: {len(tweets)}/{max_count}")
            
            if len(new_tweets) == 0 and scroll_count > 2:
                break
        
        return tweets[:max_count]

    async def scrape_retweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """爬取用户转推"""
        print(f"🔄 爬取 @{username} 的转推...")
        
        tweets = []
        scroll_count = 0
        max_scrolls = (max_count // 20) + 5
        
        await self.page.goto(f"https://twitter.com/{username}/with_replies", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        while len(tweets) < max_count and scroll_count < max_scrolls:
            await self.page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(random.uniform(2, 4))
            scroll_count += 1
            
            new_tweets = await self._parse_tweets(download_images=True)
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
            
            print(f"   已爬取: {len(tweets)}/{max_count}")
        
        return [t for t in tweets if t.is_retweet][:max_count]

    async def scrape_bookmarks(self, max_count: int = 100) -> List[Tweet]:
        """爬取书签"""
        if not self.is_logged_in:
            print("⚠️ 需要登录才能爬取书签")
            return []
        
        print(f"⭐ 爬取书签...")
        tweets = []
        scroll_count = 0
        max_scrolls = (max_count // 20) + 5
        
        await self.page.goto("https://twitter.com/i/bookmarks", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        while len(tweets) < max_count and scroll_count < max_scrolls:
            await self.page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(random.uniform(2, 4))
            scroll_count += 1
            
            new_tweets = await self._parse_tweets(download_images=True)
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
            
            print(f"   已爬取: {len(tweets)}/{max_count}")
        
        return tweets[:max_count]

    async def _parse_tweets(self, download_images: bool = True) -> List[Tweet]:
        """解析页面推文"""
        tweets = []
        try:
            elements = await self.page.query_selector_all('article[data-testid="tweet"]')
            for element in elements:
                try:
                    tweet = await self._parse_tweet_element(element, download_images)
                    if tweet:
                        tweets.append(tweet)
                except:
                    continue
        except Exception as e:
            print(f"⚠️ 解析出错: {e}")
        return tweets

    async def _parse_tweet_element(self, element, download_images: bool = True) -> Optional[Tweet]:
        """解析单个推文"""
        try:
            content_elem = await element.query_selector('[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""
            
            author_elem = await element.query_selector('[data-testid="User-Name"]')
            if author_elem:
                author_text = await author_elem.inner_text()
                lines = author_text.split('\n')
                author = lines[0] if lines else "Unknown"
                author_handle = lines[1] if len(lines) > 1 else "Unknown"
            else:
                author = "Unknown"
                author_handle = "Unknown"
            
            time_elem = await element.query_selector('time')
            created_at = await time_elem.get_attribute('datetime') if time_elem else ""
            
            likes = await self._get_interaction_count(element, 'Like')
            retweets = await self._get_interaction_count(element, 'Retweet')
            replies = await self._get_interaction_count(element, 'Reply')
            
            link_elem = await element.query_selector('a[href*="/status/"]')
            url = await link_elem.get_attribute('href') if link_elem else ""
            tweet_id = url.split('/')[-1] if url else ""
            full_url = f"https://twitter.com{url}" if url and not url.startswith('http') else url
            
            images = []
            if download_images:
                images = await self._extract_images(element, tweet_id)
            
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
        """提取并下载高清图片"""
        images = []
        try:
            img_elements = await element.query_selector_all('img[src*="media"]')
            
            for i, img in enumerate(img_elements):
                src = await img.get_attribute('src')
                if src and 'profile' not in src:
                    # 下载高清图片
                    local_path = await self._download_image_hd(src, tweet_id, i)
                    if local_path:
                        images.append(local_path)
                    self._random_delay()
        except:
            pass
        return images

    async def _download_image_hd(self, url: str, tweet_id: str, index: int) -> Optional[str]:
        """下载高清图片"""
        try:
            # 尝试获取最高清版本
            # Twitter 图片 URL 格式: .../media/xxx.jpg?name=small|medium|large|orig
            url = url.replace('&name=small', '&name=orig')
            url = url.replace('&name=medium', '&name=orig')
            url = url.replace('&name=large', '&name=orig')
            
            # 如果没有 name 参数，添加 orig
            if 'name=' not in url:
                separator = '&' if '?' in url else '?'
                url = f"{url}{separator}name=orig"
            
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                ext = 'jpg' if 'image/jpeg' in response.headers.get('content-type', '') else 'png'
                filename = f"{tweet_id}_{index}.{ext}"
                filepath = self.images_dir / filename
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                print(f"     📥 下载高清图片: {filename} ({len(response.content)//1024}KB)")
                return str(filepath)
        except Exception as e:
            print(f"     ⚠️ 下载失败: {e}")
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

    def _random_delay(self):
        """随机延时"""
        time.sleep(random.uniform(1, 3))

    async def save_to_json(self, tweets: List[Tweet], filename: str):
        """保存JSON"""
        output_path = self.output_dir / filename
        data = []
        for tweet in tweets:
            t = asdict(tweet)
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

    def generate_pdf_hd(self, tweets: List[Tweet], username: str, title: str = "Twitter 推文") -> str:
        """生成高清大图 PDF 报告"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm, mm
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
            from reportlab.lib import colors
            from PIL import Image as PILImage
        except ImportError:
            print("⚠️ 需要安装: pip install reportlab pillow")
            return None
        
        print("📄 生成高清 PDF 报告...")
        
        pdf_path = self.output_dir / f"{username}_report_hd.pdf"
        
        # A4 纸张
        page_width, page_height = A4
        margin = 1.5 * cm
        
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # 自定义样式
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'], fontSize=20)
        
        # 标题
        story.append(Paragraph(f"📘 {title}", title_style))
        story.append(Paragraph(f"@{username}", styles['Normal']))
        story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        story.append(Paragraph(f"共 {len(tweets)} 条推文", styles['Normal']))
        story.append(Spacer(1, 1*cm))
        
        # 每条推文
        for i, tweet in enumerate(tweets):
            # 标题
            story.append(Paragraph(f"#{i+1} {tweet.created_at[:10]}", styles['Heading3']))
            
            # 文字内容
            text = tweet.content[:300] + "..." if len(tweet.content) > 300 else tweet.content
            story.append(Paragraph(text.replace('\n', '<br/>'), styles['Normal']))
            
            # 互动数据
            stats = f"❤️ {tweet.likes} | 🔄 {tweet.retweets} | 💬 {tweet.replies}"
            story.append(Paragraph(stats, styles['Normal']))
            
            # 高清大图 - 占满页面宽度
            if tweet.images:
                story.append(Paragraph(f"📸 附件图片 ({len(tweet.images)}张)", styles['Normal']))
                
                for img_path in tweet.images[:4]:
                    try:
                        pil_img = PILImage.open(img_path)
                        img_w, img_h = pil_img.size
                        
                        # 计算最大显示尺寸（页面宽度减去边距）
                        max_width = page_width - 2 * margin
                        max_height = 10 * cm  # 最大高度10cm
                        
                        # 按比例缩放
                        ratio = min(max_width / img_w, max_height / img_h)
                        display_w = img_w * ratio
                        display_h = img_h * ratio
                        
                        img = Image(img_path, width=display_w, height=display_h)
                        story.append(img)
                    except Exception as e:
                        print(f"   ⚠️ 图片加载失败: {e}")
            
            # 链接
            story.append(Paragraph(f'<link href="{tweet.url}">🔗 查看原文</link>', styles['Normal']))
            story.append(Spacer(1, 0.5*cm))
            
            # 每3条推文分页
            if i % 3 == 2:
                story.append(PageBreak())
        
        doc.build(story)
        print(f"✅ 高清 PDF 已生成: {pdf_path}")
        return str(pdf_path)

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("👋 浏览器已关闭")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Twitter 爬虫 v4 - 高清图片版')
    parser.add_argument('--username', '-u', type=str, help='Twitter 用户名（不含 @）')
    parser.add_argument('--type', '-t', type=str,
                       choices=['tweets', 'retweets', 'bookmarks', 'all'],
                       default='all',
                       help='爬取类型')
    parser.add_argument('--max-count', '-m', type=int, default=50,
                       help='最大爬取数量（默认50）')
    parser.add_argument('--username-login', type=str, help='登录用户名')
    parser.add_argument('--password', type=str, help='登录密码')
    parser.add_argument('--pdf', action='store_true', help='生成 PDF')
    parser.add_argument('--no-images', action='store_true', help='不下载图片')

    args = parser.parse_args()

    if args.type in ['retweets'] and not args.username:
        print("❌ 需要指定 --username")
        sys.exit(1)

    scraper = TwitterScraperV4(headless=False, slow_mo=100)

    try:
        await scraper.init_browser()

        cookies_path = "twitter_cookies.json"
        await scraper.login(
            username=args.username_login,
            password=args.password,
            cookies_path=cookies_path
        )

        if not args.username:
            args.username = input("\n请输入 Twitter 用户名（不含 @）: ").strip()

        if args.type in ['tweets', 'all']:
            print("\n📝 爬取发帖...")
            tweets = await scraper.scrape_profile_tweets(args.username, args.max_count)
            if tweets:
                await scraper.save_to_json(tweets, f"{args.username}_tweets.json")
                await scraper.save_to_csv(tweets, f"{args.username}_tweets.csv")
                if args.pdf:
                    scraper.generate_pdf_hd(tweets, args.username, "用户发帖")

        if args.type in ['retweets', 'all']:
            print("\n🔄 爬取转推...")
            retweets = await scraper.scrape_retweets(args.username, args.max_count)
            if retweets:
                await scraper.save_to_json(retweets, f"{args.username}_retweets.json")
                if args.pdf:
                    scraper.generate_pdf_hd(retweets, args.username, "用户转推")

        if args.type in ['bookmarks', 'all']:
            if scraper.is_logged_in:
                print("\n⭐ 爬取书签...")
                bookmarks = await scraper.scrape_bookmarks(args.max_count)
                if bookmarks:
                    await scraper.save_to_json(bookmarks, "bookmarks.json")
                    await scraper.save_to_csv(bookmarks, "bookmarks.csv")
                    if args.pdf:
                        scraper.generate_pdf_hd(bookmarks, "bookmarks", "收藏书签")

        print("\n🎉 完成！")
        print(f"📂 数据保存在: {scraper.output_dir}")
        input("\n按 Enter 关闭浏览器...")

    except KeyboardInterrupt:
        print("\n⚠️ 已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
