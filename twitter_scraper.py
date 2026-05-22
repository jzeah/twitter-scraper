"""
Twitter 爬虫工具
模拟人类浏览行为，以正常速度爬取数据，避免被封禁
"""
import asyncio
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

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
    特点：
    - 模拟真实浏览器行为
    - 随机延时避免被封
    - 支持登录后爬取私有数据
    """
    
    def __init__(self, headless: bool = True, slow_mo: int = 100):
        """
        初始化爬虫
        
        Args:
            headless: 是否无头模式（无界面）
            slow_mo: 操作间隔（毫秒），模拟人类操作速度
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False
        
        # 防封策略配置
        self.min_delay = 3  # 最小延时（秒）
        self.max_delay = 8  # 最大延时（秒）
        
        # 数据保存路径
        self.output_dir = Path("assets/twitter_data")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def init_browser(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        
        # 创建浏览器上下文（隔离环境）
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
        """随机延时（模拟人类阅读速度）"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"⏱️  等待 {delay:.1f} 秒...")
        time.sleep(delay)
    
    async def login(self, username: str = None, password: str = None, cookies_path: str = None):
        """
        登录 Twitter
        
        Args:
            username: 用户名/邮箱/手机号
            password: 密码
            cookies_path: 保存/加载 cookies 的路径
        """
        print("🔐 开始登录 Twitter...")
        
        # 尝试加载已保存的 cookies
        if cookies_path and os.path.exists(cookies_path):
            print("📂 加载已保存的 cookies...")
            with open(cookies_path, 'r') as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            await self.page.goto("https://twitter.com/home")
            await asyncio.sleep(3)
            
            # 验证是否登录成功
            if await self._check_login_status():
                print("✅ 已通过 cookies 登录成功")
                self.is_logged_in = True
                return True
        
        # 需要手动登录
        await self.page.goto("https://twitter.com/login")
        await asyncio.sleep(2)
        
        if username and password:
            print(f"📝 使用账号密码登录: {username}")
            await self._login_with_credentials(username, password)
        else:
            print("⚠️  未提供账号密码，请在弹出的浏览器窗口中扫码登录")
            print("⏳ 等待登录完成...")
            # 等待用户扫码
            await asyncio.sleep(60)
        
        # 验证登录状态
        if await self._check_login_status():
            print("✅ 登录成功！")
            self.is_logged_in = True
            
            # 保存 cookies
            if cookies_path:
                await self._save_cookies(cookies_path)
        else:
            print("❌ 登录失败")
        
        return self.is_logged_in
    
    async def _login_with_credentials(self, username: str, password: str):
        """使用账号密码登录"""
        await asyncio.sleep(2)
        
        # 输入用户名
        await self.page.fill('input[autocomplete="username"]', username)
        await asyncio.sleep(1)
        
        # 点击下一步或直接输入密码（Twitter 会根据情况要求手机验证）
        next_btn = self.page.locator('button:has-text("下一步"), button:has-text("Next")')
        if await next_btn.is_visible():
            await next_btn.click()
            await asyncio.sleep(2)
        
        # 输入密码
        await self.page.fill('input[name="password"]', password)
        await asyncio.sleep(1)
        
        # 点击登录
        login_btn = self.page.locator('button:has-text("登录"), button:has-text("Log in")')
        await login_btn.click()
        await asyncio.sleep(3)
    
    async def _check_login_status(self) -> bool:
        """检查登录状态"""
        try:
            await self.page.goto("https://twitter.com/home", timeout=10000)
            await asyncio.sleep(2)
            
            # 检查是否跳转到登录页
            if "login" in self.page.url:
                return False
            
            # 检查是否有用户头像或设置按钮
            profile_btn = self.page.locator('[data-testid="UserAvatar"]')
            return await profile_btn.count() > 0
        except:
            return False
    
    async def _save_cookies(self, path: str):
        """保存 cookies"""
        cookies = await self.context.cookies()
        with open(path, 'w') as f:
            json.dump(cookies, f)
        print(f"💾 Cookies 已保存到: {path}")
    
    async def scrape_profile_tweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """
        爬取用户发帖
        
        Args:
            username: Twitter 用户名（不含 @）
            max_count: 最大爬取数量
        
        Returns:
            推文列表
        """
        print(f"📥 开始爬取用户 @{username} 的发帖...")
        
        tweets = []
        url = f"https://twitter.com/{username}"
        await self.page.goto(url)
        
        # 等待页面加载
        await asyncio.sleep(3)
        
        # 滚动加载更多推文
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = (max_count // 10) + 5  # 估算需要的滚动次数
        
        while scroll_attempts < max_scroll_attempts and len(tweets) < max_count:
            # 滚动到页面底部
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            
            # 等待新内容加载
            await asyncio.sleep(2)
            
            # 解析当前可见的推文
            new_tweets = await self._parse_tweets_from_page(username)
            
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ 解析推文: {tweet.content[:50]}...")
            
            # 检查是否还有新内容
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
                print(f"  ⏳ 页面高度未变，尝试第 {scroll_attempts} 次...")
            else:
                scroll_attempts = 0
            
            last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条发帖")
        return tweets[:max_count]
    
    async def scrape_retweets(self, username: str, max_count: int = 100) -> List[Tweet]:
        """
        爬取用户转发的推文
        
        Args:
            username: Twitter 用户名
            max_count: 最大爬取数量
        
        Returns:
            转发列表
        """
        print(f"📥 开始爬取用户 @{username} 的转推...")
        
        tweets = []
        url = f"https://twitter.com/{username}/with_replies"
        await self.page.goto(url)
        await asyncio.sleep(3)
        
        # 滚动加载
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = (max_count // 10) + 5
        
        while scroll_attempts < max_scroll_attempts and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            # 解析推文
            new_tweets = await self._parse_tweets_from_page(username)
            
            # 过滤出转发的推文
            for tweet in new_tweets:
                if tweet.is_retweet and tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ 解析转推: {tweet.content[:50]}...")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            
            last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条转推")
        return tweets[:max_count]
    
    async def scrape_bookmarks(self, max_count: int = 100) -> List[Tweet]:
        """
        爬取用户书签
        
        Returns:
            书签列表
        """
        if not self.is_logged_in:
            print("❌ 需要登录才能访问书签")
            return []
        
        print(f"📥 开始爬取书签...")
        
        tweets = []
        await self.page.goto("https://twitter.com/i/bookmarks")
        await asyncio.sleep(3)
        
        # 滚动加载
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = (max_count // 10) + 5
        
        while scroll_attempts < max_scroll_attempts and len(tweets) < max_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._random_delay()
            await asyncio.sleep(2)
            
            # 解析推文
            new_tweets = await self._parse_bookmarks_from_page()
            
            for tweet in new_tweets:
                if tweet not in tweets:
                    tweets.append(tweet)
                    print(f"  ✅ 解析书签: {tweet.content[:50]}...")
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            
            last_height = new_height
        
        print(f"✅ 共爬取 {len(tweets)} 条书签")
        return tweets[:max_count]
    
    async def _parse_tweets_from_page(self, username: str) -> List[Tweet]:
        """解析页面上的推文"""
        tweets = []
        
        try:
            # 等待推文加载
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=5000)
            
            # 查找所有推文元素
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')
            
            for element in tweet_elements:
                try:
                    tweet = await self._parse_tweet_element(element, username)
                    if tweet:
                        tweets.append(tweet)
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"⚠️  解析推文时出错: {e}")
        
        return tweets
    
    async def _parse_tweet_element(self, element, default_username: str) -> Optional[Tweet]:
        """解析单个推文元素"""
        try:
            # 获取推文内容
            content_elem = await element.query_selector('[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""
            
            # 获取作者信息
            author_elem = await element.query_selector('[data-testid="User-Name"]')
            if author_elem:
                author_text = await author_elem.inner_text()
                # 解析作者名称和 handle
                lines = author_text.split('\n')
                author = lines[0] if lines else default_username
                handle = lines[1] if len(lines) > 1 else default_username
            else:
                author = default_username
                handle = default_username
            
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
            
            # 检查是否是转推
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
                author_handle=handle,
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
    
    async def _parse_bookmarks_from_page(self) -> List[Tweet]:
        """解析书签页面"""
        tweets = []
        
        try:
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=5000)
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')
            
            for element in tweet_elements:
                tweet = await self._parse_tweet_element(element, "bookmark")
                if tweet:
                    tweets.append(tweet)
        
        except Exception as e:
            print(f"⚠️  解析书签时出错: {e}")
        
        return tweets
    
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
        """解析数字（处理 K、M 等单位）"""
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
        """保存为 JSON 文件"""
        output_path = self.output_dir / filename
        data = [asdict(tweet) for tweet in tweets]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 数据已保存到: {output_path}")
        return str(output_path)
    
    async def save_to_csv(self, tweets: List[Tweet], filename: str):
        """保存为 CSV 文件"""
        output_path = self.output_dir / filename
        df = pd.DataFrame([asdict(tweet) for tweet in tweets])
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"💾 数据已保存到: {output_path}")
        return str(output_path)


async def main():
    """主函数"""
    scraper = TwitterScraper(headless=False, slow_mo=100)
    
    try:
        await scraper.init_browser()
        
        # 登录（使用已保存的 cookies 或手动扫码）
        cookies_path = "assets/twitter_cookies.json"
        await scraper.login(cookies_path=cookies_path)
        
        username = input("\n请输入要爬取的 Twitter 用户名（不含 @）: ").strip()
        if not username:
            print("❌ 用户名不能为空")
            return
        
        # 爬取发帖
        tweets = await scraper.scrape_profile_tweets(username, max_count=50)
        if tweets:
            await scraper.save_to_json(tweets, f"{username}_tweets.json")
            await scraper.save_to_csv(tweets, f"{username}_tweets.csv")
        
        # 爬取转推
        retweets = await scraper.scrape_retweets(username, max_count=50)
        if retweets:
            await scraper.save_to_json(retweets, f"{username}_retweets.json")
        
        # 爬取书签（仅登录用户）
        if scraper.is_logged_in:
            bookmarks = await scraper.scrape_bookmarks(max_count=50)
            if bookmarks:
                await scraper.save_to_json(bookmarks, f"{username}_bookmarks.json")
        
        print("\n🎉 爬取完成！")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
