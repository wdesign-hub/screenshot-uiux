from selenium import webdriver
from urllib.parse import urljoin, urlparse
from tqdm import tqdm  
import base64
import time
import re
import os
import tkinter as tk
from tkinter import filedialog

def clean_filename(url):
    """Converts a URL into a safe file name."""
    clean = re.sub(r'[\\/*?:"<>|]', "", url.replace("https://", "").replace("http://", ""))
    return clean[:50] + ".png" 

def smooth_scroll(driver):
    """Physically scrolls the page to trigger animations and lazy loading, then resets."""
    total_height = driver.execute_script("return document.body.scrollHeight")
    viewport_height = driver.execute_script("return window.innerHeight")
    
    current_position = 0
    while current_position < total_height:
        current_position += viewport_height
        driver.execute_script(f"window.scrollTo(0, {current_position});")
        time.sleep(0.5) 
        total_height = driver.execute_script("return document.body.scrollHeight")

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

def remove_popups(driver):
    """Injects JavaScript to find and delete common fixed popups and cookie banners."""
    js_code = """
    const selectors = [
        '[id*="cookie"]', '[class*="cookie"]', 
        '[id*="consent"]', '[class*="consent"]',
        '[id*="popup"]', '[class*="popup"]',
        '[id*="banner"]', '[class*="banner"]'
    ];
    selectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(el => {
            const style = window.getComputedStyle(el);
            if (style.position === 'fixed' || style.position === 'sticky') {
                el.remove();
            }
        });
    });
    """
    driver.execute_script(js_code)
    time.sleep(1)

def crawl_and_snap():
    # 1. Ask for URL and Limit
    start_url = input("Enter the starting URL (e.g., https://example.com): ").strip()
    
    try:
        limit = int(input("Enter the maximum number of pages to capture: ").strip())
    except ValueError:
        print("Invalid number. Defaulting to 5.")
        limit = 5

    domain = urlparse(start_url).netloc
    
    # 2. GUI FOLDER SELECTION
    print("\nOpening folder selection dialog...")
    
    # Set up the hidden tkinter window
    root = tk.Tk()
    root.withdraw() # Hides the main empty GUI window
    root.attributes('-topmost', True) # Forces the dialog to open in front of your terminal
    
    # Open the native OS folder picker
    folder_path = filedialog.askdirectory(title="Select Folder to Save Screenshots")
    
    # If you click "Cancel" on the dialog, it defaults back to creating a folder in the current directory
    if not folder_path:
        print("No folder selected. Defaulting to the website's domain name...")
        folder_path = domain 
        os.makedirs(folder_path, exist_ok=True)
        
    print(f"\nAll screenshots will be saved to: {folder_path}")

    # 3. Set up the crawler
    visited = set()
    queue = [start_url]
    captured_count = 0

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--hide-scrollbars") 
    options.add_argument("--log-level=3") 
    
    print("\nStarting browser...")
    driver = webdriver.Chrome(options=options)

    print("\n") 
    pbar = tqdm(total=limit, desc="Capturing", unit="page", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

    # 4. Run the crawl loop
    try:
        while queue and captured_count < limit:
            current_url = queue.pop(0)
            
            if current_url in visited or "#" in current_url:
                continue
                
            visited.add(current_url)
            
            short_url = current_url.replace("https://", "").replace("http://", "")[:35]
            pbar.set_description(f"Snapping: {short_url:<35}")
            
            driver.get(current_url)
            time.sleep(3) 
            
            # Extract internal links
            hrefs = driver.execute_script(
                "return Array.from(document.querySelectorAll('a')).map(a => a.href);"
            )
            
            for href in hrefs:
                if href:
                    full_url = urljoin(current_url, href)
                    if urlparse(full_url).netloc == domain and full_url not in visited:
                        if full_url not in queue:
                            queue.append(full_url)

            # Prepare the page
            smooth_scroll(driver)
            remove_popups(driver)

            # Capture the screenshot
            try:
                metrics = driver.execute_cdp_cmd('Page.getLayoutMetrics', {})
                width = metrics['contentSize']['width']
                height = metrics['contentSize']['height']
                
                screenshot_data = driver.execute_cdp_cmd('Page.captureScreenshot', {
                    'clip': {'x': 0, 'y': 0, 'width': width, 'height': height, 'scale': 1},
                    'captureBeyondViewport': True
                })
                
                # Save to the selected folder
                filename = clean_filename(current_url)
                filepath = os.path.join(folder_path, filename) 
                
                with open(filepath, "wb") as file:
                    file.write(base64.b64decode(screenshot_data['data']))

                captured_count += 1
                pbar.update(1) 
                
            except Exception as e:
                tqdm.write(f"\nError capturing {current_url}: {e}")

    finally:
        pbar.close() 
        print("\nFinished! Closing browser.")
        driver.quit()

if __name__ == "__main__":
    crawl_and_snap()