"""
Twitter 爬虫工具 v2
修复登录和解析问题
"""
import asyncio
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
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
    is_retweet: bool = False
    original_author: Optional[str] = None
    scraped_at: str = ""


class TwitterScraper:
    """
    Twitter 爬虫工具
    """
    
    def __init__(self, headless: bool = False, slow_mo: int = 100):
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        
        # 防封策略配置
        self.min_delay = 2  # 最小延时（秒）
        self.max_delay = 5  # 最大延时（秒）
        
        # 数据保存路径
        self.output_dir = Path("assets/twitter_data")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
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
        """
        登录 Twitter
        """
        print("🔐 开始登录 Twitter...")
        
        # 尝试加载 cookies
        if cookies_path and os.path.exists(cookies_path):
            print("📂 加载已保存的 cookies...")
            with open(cookies_path, 'r') as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            await self.page.goto("https://twitter.com/home")
            await asyncio.sleep(3)
            
            # 验证是否已登录
            if "login" not in self.page.url:
                print("✅ 已通过 cookies 登录成功")
                self.is_logged_in = True
                return True
        
        # 手动登录
        await self.page.goto("https://twitter.com/login")
        await asyncio.sleep(2)
        
        if username and password:
            print(f"📝 使用账号密码登录...")
            await self._login_with_credentials(username, password)
        else:
            print("⚠️  未提供账号密码，请在浏览器中登录")
            print("⏳ 等待登录完成（按 Enter 继续）...")
            # 等待用户登录 - 用户按 Enter 继续
            input()
        
        # 跳转到首页检查
        await self.page.goto("https://twitter.com/home")
        await asyncio.sleep(3)
        
        # 检查是否登录成功
        if "login" not in self.page.url:
            print("✅ 登录成功！")
            self.is_logged_in = True
            
            # 保存 cookies
            if cookies_path:
                await self._save_cookies(cookies_path)
        else:
            print("❌ 登录失败，请重试")
        
        return self.is_logged_in
    
    async def _login_with_credentials(self, username: str, password: str):
        """使用账号密码登录"""
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
        """保存 cookies"""
        cookies = await self.context.cookies()
        with open(path, 'w') as f:
            json.dump(cookies, f)
        print(f"💾 Cookies 已保存到: {path}")
    
    async def scrape_profile_tweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """爬取用户发帖"""
        print(f"📥 开始爬取用户 @{username} 的发帖...")
        
        tweets = []
        url = f"https://twitter.com/{username}"
        await self.page.goto(url)
        await asyncio.sleep(3)
        
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            print(f"📜 滚动第 {scroll_count + 1} 次...")
            
            # 滚动页面
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            # 解析推文
            new_tweets = await self._parse_tweets_from_page()
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ 找到推文: {tweet.content[:30]}...")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            # 检查是否到达底部
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条发帖")
        return tweets[:max_count]
    
    async def scrape_retweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """爬取转推"""
        print(f"📥 开始爬取转推...")
        
        tweets = []
        await self.page.goto(f"https://twitter.com/{username}")
        await asyncio.sleep(3)
        
        # 点击"帖子"标签获取所有内容
        try:
            posts_tab = self.page.locator('a:has-text("Posts"), a:has-text("帖子")')
            if await posts_tab.count() > 0:
                await posts_tab.first.click()
                await asyncio.sleep(2)
        except:
            pass
        
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            new_tweets = await self._parse_tweets_from_page()
            for tweet in new_tweets:
                if tweet not in tweets and tweet.is_retweet:
                    tweets.append(tweet)
                    print(f"  ✅ 找到转推: {tweet.content[:30]}...")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条转推")
        return tweets[:max_count]
    
    async def scrape_bookmarks(self, max_count: int = 100) -> List[Tweet]:
        """爬取书签"""
        if not self.is_logged_in:
            print("❌ 需要登录才能访问书签")
            return []
        
        print(f"📥 开始爬取书签...")
        await self.page.goto("https://twitter.com/i/bookmarks")
        await asyncio.sleep(3)
        
        tweets = []
        last_height = 0
        scroll_count = 0
        max_scroll = (max_count // 10) + 10
        
        while scroll_count < max_scroll and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            new_tweets = await self._parse_tweets_from_page()
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ 找到书签: {tweet.content[:30]}...")
            
            print(f"  📊 当前: {len(tweets)} 条")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_count += 1
            else:
                scroll_count = 0
                last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条书签")
        return tweets[:max_count]
    
    async def _parse_tweets_from_page(self) -> List[Tweet]:
        """解析页面上的推文"""
        tweets = []
        
        try:
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=5000)
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')
            
            for element in tweet_elements:
                try:
                    tweet = await self._parse_tweet_element(element)
                    if tweet:
                        tweets.append(tweet)
                except:
                    continue
        
        except Exception as e:
            print(f"⚠️  解析推文时出错: {e}")
        
        return tweets
    
    async def _parse_tweet_element(self, element) -> Optional[Tweet]:
        """解析单个推文"""
        try:
            # 获取推文内容
            content_elem = await element.query_selector('[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""
            
            # 获取作者信息
            author_elem = await element.query_selector('[data-testid="User-Name"]')
            if author_elem:
                author_text = await author_elem.inner_text()
                lines = author_text.split('\n')
                author = lines[0] if lines else "Unknown"
                author_handle = lines[1] if len(lines) > 1 else "Unknown"
            else:
                author = "Unknown"
                author_handle = "Unknown"
            
            # 获取时间
            time_elem = await element.query_selector('time')
            created_at = await time_elem.get_attribute('datetime') if time_elem else ""
            
            # 获取互动数据
            likes = await self._get_interaction_count(element, 'Like')
            retweets = await self._get_interaction_count(element, 'Retweet')
            replies = await self._get_interaction_count(element, 'Reply')
            
            # 获取推文链接
            link_elem = await element.query_selector('a[href*="/status/"]')
            url = await link_elem.get_attribute('href') if link_elem else ""
            tweet_id = url.split('/')[-1] if url else ""
            full_url = f"https://twitter.com{url}" if url and not url.startswith('http') else url
            
            # 检查是否转推
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
                is_retweet=is_retweet,
                original_author=original_author,
                scraped_at=datetime.now().isoformat()
            )
        
        except Exception as e:
            return None
    
    async def _get_interaction_count(self, element, interaction_type: str) -> int:
        """获取互动数量"""
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
        else:
            try:
                return int(text)
            except:
                return 0
    
    async def save_to_json(self, tweets: List[Tweet], filename: str):
        """保存为 JSON"""
        output_path = self.output_dir / filename
        data = [asdict(tweet) for tweet in tweets]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 已保存: {output_path}")
        return str(output_path)
    
    async def save_to_csv(self, tweets: List[Tweet], filename: str):
        """保存为 CSV"""
        output_path = self.output_dir / filename
        df = pd.DataFrame([asdict(tweet) for tweet in tweets])
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"💾 已保存: {output_path}")
        return str(output_path)
