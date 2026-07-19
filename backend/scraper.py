import os
import re
import asyncio
import requests
from playwright.async_api import async_playwright

def clean_pinterest_url(url):
    """
    Converts a low/medium resolution pin image URL to the original high-resolution version.
    Example:
    https://i.pinimg.com/236x/ab/cd/ef/abcdef.jpg -> https://i.pinimg.com/originals/ab/cd/ef/abcdef.jpg
    """
    if not url:
        return ""
    # Replace resolution path (e.g. 236x, 474x, 564x, 736x, 60x60, 150x150) with originals
    url = re.sub(r'/xxs/|/xs/|/s/|/m/|/l/|/\d+x\d*/', '/originals/', url)
    return url

async def scrape_direct_pinterest(page, query, limit=10):
    """
    Attempts to search Pinterest directly. Scrolls dynamically based on requested limit.
    """
    print(f"Scraping Pinterest directly for: '{query}' (limit: {limit})")
    search_url = f"https://www.pinterest.com/search/pins/?q={requests.utils.quote(query)}"
    await page.goto(search_url, wait_until="domcontentloaded")
    
    # Wait up to 5 seconds for images to appear
    try:
        await page.wait_for_selector("img[src*='i.pinimg.com']", timeout=5000)
    except Exception:
        print("Timeout waiting for images on Pinterest direct search.")
        
    # Scroll dynamically based on the requested limit to load more images
    scroll_times = max(1, min(15, (limit // 8) + 1))
    for scroll in range(scroll_times):
        await page.evaluate("window.scrollBy(0, 1000)")
        await asyncio.sleep(1.2)
    
    # Extract image sources
    images = await page.locator("img").all()
    results = []
    seen = set()
    
    for img in images:
        try:
            src = await img.get_attribute("src")
            alt = await img.get_attribute("alt") or "Pinterest Image"
            if src and "i.pinimg.com" in src:
                # Skip profile pictures, avatars, and icons
                if any(avatar_indicator in src for avatar_indicator in ["/60x60/", "/75x75/", "/150x150/", "/user/", "profile"]):
                    continue
                    
                high_res = clean_pinterest_url(src)
                if high_res not in seen:
                    seen.add(high_res)
                    results.append({
                        "url": high_res,
                        "title": alt,
                        "source": "pinterest"
                    })
        except Exception:
            continue
            
    return results

async def scrape_ddg_fallback(page, query, limit=10):
    """
    Falls back to DuckDuckGo Image Search to find Pinterest pins.
    Highly reliable when Pinterest blocks bots.
    """
    print(f"Scraping DuckDuckGo fallback for: '{query}' (limit: {limit})")
    ddg_query = f"{query} site:pinterest.com"
    search_url = f"https://duckduckgo.com/?q={requests.utils.quote(ddg_query)}&iax=images&ia=images"
    await page.goto(search_url, wait_until="domcontentloaded")
    
    # Wait for image container to load
    try:
        await page.wait_for_selector(".tile--img img", timeout=5000)
    except Exception:
        print("Timeout waiting for images on DuckDuckGo fallback.")
        
    # Scroll dynamically based on the requested limit to load more images
    scroll_times = max(1, min(15, (limit // 8) + 1))
    for scroll in range(scroll_times):
        await page.evaluate("window.scrollBy(0, 1200)")
        await asyncio.sleep(1.2)
    
    # Extract links from tile containers which contain direct Pinterest source URLs
    tiles = await page.locator("a.tile--img__link").all()
    results = []
    seen = set()
    
    for tile in tiles:
        try:
            href = await tile.get_attribute("href")
            if href:
                if "media_url=" in href:
                    media_url_match = re.search(r"media_url=([^&]+)", href)
                    if media_url_match:
                        decoded_url = requests.utils.unquote(media_url_match.group(1))
                        if "i.pinimg.com" in decoded_url:
                            # Skip profile pictures, avatars, and icons
                            if any(avatar_indicator in decoded_url for avatar_indicator in ["/60x60/", "/75x75/", "/150x150/", "/user/", "profile"]):
                                continue
                                
                            high_res = clean_pinterest_url(decoded_url)
                            if high_res not in seen:
                                seen.add(high_res)
                                results.append({
                                    "url": high_res,
                                    "title": "Pinterest Image",
                                    "source": "ddg_pinterest"
                                })
        except Exception:
            continue
            
    return results

def download_image(url, output_path):
    """
    Downloads an image from the given URL and saves it to output_path.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Referer': 'https://www.pinterest.com/'
    }
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        if "image" in response.headers.get("Content-Type", ""):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
    print(f"Failed to download image. Status: {response.status_code}")
    return False

async def search_pinterest_images(query, limit=10):
    """
    Searches Pinterest and/or DuckDuckGo fallback, and returns a list of unique,
    cleaned high-resolution image metadata dictionaries.
    """
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        # Use a realistic viewport and User-Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        results = []
        try:
            # 1. Try direct Pinterest scraping
            results = await scrape_direct_pinterest(page, query, limit)
        except Exception as e:
            print(f"Direct Pinterest scraping failed: {e}")
            
        # If we have fewer than limit results, run DuckDuckGo fallback
        if len(results) < limit:
            try:
                fallback_results = await scrape_ddg_fallback(page, query, limit)
                seen_urls = {item["url"] for item in results}
                for res in fallback_results:
                    if res["url"] not in seen_urls:
                        seen_urls.add(res["url"])
                        results.append(res)
            except Exception as e:
                print(f"DDG fallback scraping failed: {e}")
                
        await browser.close()
        
    return results
