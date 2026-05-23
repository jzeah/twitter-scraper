#!/usr/bin/env python
"""
Twitter 爬虫 v3
支持图片下载、PDF生成、GitHub上传
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from twitter_scraper_v3 import TwitterScraper


async def main():
    parser = argparse.ArgumentParser(description='Twitter 爬虫 v3')
    parser.add_argument('--username', '-u', type=str, help='Twitter 用户名')
    parser.add_argument('--type', '-t', type=str, 
                       choices=['tweets', 'retweets', 'bookmarks', 'all'],
                       default='all')
    parser.add_argument('--max-count', '-m', type=int, default=20)
    parser.add_argument('--username-login', type=str, help='登录用户名')
    parser.add_argument('--password', type=str, help='登录密码')
    parser.add_argument('--no-images', action='store_true', help='不下载图片')
    parser.add_argument('--pdf', action='store_true', help='生成PDF')
    parser.add_argument('--upload', type=str, help='GitHub上传 (格式: owner/repo)')
    parser.add_argument('--token', type=str, help='GitHub Token')

    args = parser.parse_args()

    scraper = TwitterScraper(headless=False, slow_mo=100)
    download_images = not args.no_images

    try:
        await scraper.init_browser()
        cookies_path = "twitter_cookies.json"
        await scraper.login(args.username_login, args.password, cookies_path)

        if not args.username:
            args.username = input("\n用户名: ").strip()

        results = {}
        pdf_path = None

        # 爬取发帖
        if args.type in ['tweets', 'all']:
            print("\n" + "="*50)
            print("📝 爬取发帖...")
            tweets = await scraper.scrape_profile_tweets(args.username, args.max_count, download_images)
            if tweets:
                json_path = await scraper.save_to_json(tweets, f"{args.username}_tweets.json")
                csv_path = await scraper.save_to_csv(tweets, f"{args.username}_tweets.csv")
                results['tweets'] = {'count': len(tweets), 'json': json_path, 'csv': csv_path}
                
                if args.pdf:
                    pdf_path = scraper.generate_pdf(tweets, args.username, "用户发帖")

        # 爬取转推
        if args.type in ['retweets', 'all']:
            print("\n" + "="*50)
            print("🔄 爬取转推...")
            retweets = await scraper.scrape_retweets(args.username, args.max_count)
            if retweets:
                json_path = await scraper.save_to_json(retweets, f"{args.username}_retweets.json")
                results['retweets'] = {'count': len(retweets), 'json': json_path}

        # 爬取书签
        if args.type in ['bookmarks', 'all']:
            if scraper.is_logged_in:
                print("\n" + "="*50)
                print("⭐ 爬取书签...")
                bookmarks = await scraper.scrape_bookmarks(args.max_count, download_images)
                if bookmarks:
                    json_path = await scraper.save_to_json(bookmarks, "bookmarks.json")
                    csv_path = await scraper.save_to_csv(bookmarks, "bookmarks.csv")
                    results['bookmarks'] = {'count': len(bookmarks), 'json': json_path, 'csv': csv_path}

        # 总结
        print("\n" + "="*50)
        print("🎉 爬取完成！")
        print("="*50)
        for key, value in results.items():
            print(f"  {key}: {value['count']} 条")
        
        if args.pdf and pdf_path:
            print(f"\n📄 PDF: {pdf_path}")
        
        # GitHub 上传
        if args.upload and args.token:
            files_to_upload = [json_path for value in results.values() for key, json_path in [('json', value.get('json'))] if json_path]
            if pdf_path:
                files_to_upload.append(pdf_path)
            
            print(f"\n📤 开始上传到 GitHub...")
            for f in files_to_upload:
                url = scraper.upload_to_github(f, args.upload, args.token)
                if url:
                    print(f"   {url}")

    except KeyboardInterrupt:
        print("\n⚠️ 已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按 Enter 关闭...")
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
