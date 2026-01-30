"""Quick test of browser-based PDF download"""
from playwright.sync_api import sync_playwright
import os
import time

def test_download():
    p = sync_playwright().start()
    # Use new headless mode which is harder to detect
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
        ]
    )
    context = browser.new_context(
        accept_downloads=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
    )
    
    # Remove webdriver flag
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    os.makedirs('test_browser', exist_ok=True)
    
    # Test with Frontiers - this should work
    article_url = 'https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2020.00066/full'
    download_path = 'test_browser/frontiers_test.pdf'
    
    print(f"Testing: {article_url}")
    
    # Set up download event
    download_complete = False
    download_path = 'test_browser/mdpi_test.pdf'
    
    def on_download(download):
        nonlocal download_complete
        print(f"  Download started: {download.suggested_filename}")
        download.save_as(download_path)
        download_complete = True
        print(f"  Download saved!")
    
    page.on('download', on_download)
    
    try:
        # Navigate to article page first
        response = page.goto(article_url, timeout=30000, wait_until='networkidle')
        print(f"  Response status: {response.status if response else 'None'}")
        print(f"  Final URL: {page.url}")
        
        # Look for PDF download link
        pdf_link = page.locator('a[href*="/pdf"]').first
        if pdf_link.count() > 0:
            href = pdf_link.get_attribute('href')
            print(f"  Found PDF link: {href}")
            
            # Navigate directly to PDF URL instead of clicking
            pdf_page = context.new_page()
            try:
                with pdf_page.expect_download(timeout=30000) as download_info:
                    pdf_page.goto(href)
                
                download = download_info.value
                download.save_as(download_path)
                download_complete = True
                print(f"  Download complete via navigation!")
            except Exception as nav_error:
                if 'Download is starting' in str(nav_error):
                    # Download was triggered, wait for it
                    time.sleep(5)
                    download_complete = True
                else:
                    # Try direct response body
                    try:
                        response = pdf_page.goto(href, timeout=30000)
                        if response and response.status == 200:
                            content_type = response.headers.get('content-type', '')
                            if 'pdf' in content_type.lower():
                                content = response.body()
                                if content[:4] == b'%PDF':
                                    with open(download_path, 'wb') as f:
                                        f.write(content)
                                    download_complete = True
                                    print(f"  Downloaded via response body!")
                    except Exception as body_error:
                        print(f"  Response body error: {body_error}")
            finally:
                pdf_page.close()
        else:
            print("  No PDF link found")
        
    except Exception as e:
        if 'Download is starting' in str(e):
            print("  Download triggered!")
            # Wait for the download event handler
            for i in range(10):
                if download_complete:
                    break
                time.sleep(1)
        else:
            print(f"  Error: {e}")
    
    # Check result
    if os.path.exists(download_path):
        size = os.path.getsize(download_path)
        print(f"\n✓ SUCCESS! Downloaded {size} bytes")
        
        # Verify it's a PDF
        with open(download_path, 'rb') as f:
            header = f.read(4)
            print(f"  Is PDF: {header == b'%PDF'}")
    else:
        print("\n✗ Download failed")
    
    context.close()
    browser.close()
    p.stop()


if __name__ == "__main__":
    test_download()
