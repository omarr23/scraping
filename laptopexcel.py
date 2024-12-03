import requests
from bs4 import BeautifulSoup
import sys
import re
import logging
import json
from fake_useragent import UserAgent
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LaptopScraper:
    def __init__(self, search_url):
        """
        Initialize the Laptop scraper with improved Arabic support

        Args:
            search_url (str): URL for laptops
        """
        self.url = search_url
        self.ua = UserAgent()

    def clean_text(self, text):
        """
        Clean and normalize text, especially for Arabic content

        Args:
            text (str): Input text to clean

        Returns:
            str: Cleaned text
        """
        if not text:
            return ''
        
        # Remove extra whitespaces
        text = ' '.join(text.split())
        
        # Normalize Arabic numerals to Western numerals
        arabic_numerals = {'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
                           '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'}
        for arabic_num, western_num in arabic_numerals.items():
            text = text.replace(arabic_num, western_num)
        
        return text

    def extract_specifications(self, description):
        """
        Extract key specifications from product description with Arabic support

        Args:
            description (str): Product description text

        Returns:
            dict: Extracted specifications
        """
        specs = {}

        # Comprehensive regex patterns for laptop specifications (supporting Arabic numerals)
        spec_patterns = [
            (r'(\d+)\s*جيجابايت\s*(?:رام|ذاكرة)', 'RAM'),
            (r'(\d+)\s*جيجابايت\s*SSD', 'SSD'),
            (r'(\d+)\s*تيرابايت\s*(?:قرص صلب|HDD)', 'HDD'),
            (r'(إنتل|Intel|AMD)\s+(?:كور|Core|رايزن|Ryzen)\s*(\w+)', 'Processor'),
            (r'(\d+(?:\.\d+)?)\s*(?:بوصة|inch)', 'Screen Size'),
            (r'(ويندوز|Windows|لينكس|Linux|ماك\s*أو\s*إس|MacOS)', 'Operating System'),
        ]

        # Combine Arabic and English patterns
        for pattern, key in spec_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                # If there are multiple groups, join them
                specs[key] = ' '.join(match.groups())
        
        return specs

    def scrape_laptop_data(self, max_pages=3):
        """
        Scrape laptop data from the site with improved Arabic support

        Args:
            max_pages (int): Maximum number of pages to scrape

        Returns:
            list: Scraped laptops
        """
        scraped_laptops = []

        for page in range(1, max_pages + 1):
            try:
                # Prepare request headers with Arabic language support
                headers = {
                    'User-Agent': self.ua.random,
                    'Accept-Language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                }

                # Modify URL for pagination and include the extra parameter
                paginated_url = f"{self.url}&p={page}" if '?_' in self.url else f"{self.url}?p={page}"

                # Send request with timeout
                response = requests.get(paginated_url, headers=headers, timeout=15)
                response.encoding = 'utf-8'  # Explicitly set UTF-8 encoding
                response.raise_for_status()

                # Parse HTML with UTF-8 support
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')

                # Find laptop product containers (adjust selectors as needed)
                product_containers = soup.find_all('li', class_=re.compile(r'item.*product'))

                if not product_containers:
                    logger.warning(f"No product containers found on page {page}")
                    continue

                for container in product_containers:
                    try:
                        # Extract product name (with Arabic support)
                        name_elem = container.find('a', class_='product-item-link')
                        if not name_elem:
                            continue

                        name = self.clean_text(name_elem.get_text(strip=True))

                        # Extract price
                        price_elem = container.find('span', class_='price')
                        price = self.clean_text(price_elem.get_text(strip=True)) if price_elem else 'N/A'

                        # Extract product link
                        product_link = name_elem['href']

                        # Fetch product page for more details
                        product_page = requests.get(product_link, headers=headers, timeout=15)
                        product_page.encoding = 'utf-8'
                        product_soup = BeautifulSoup(product_page.content, 'html.parser', from_encoding='utf-8')

                        # Extract product description
                        description_elem = product_soup.find('div', id='description')
                        description = self.clean_text(description_elem.get_text(strip=True)) if description_elem else 'No description available'

                        # Extract specifications
                        specs = self.extract_specifications(description)

                        # Create product entry
                        laptop_product = {
                            'Name': name,
                            'Price': price,
                            'Link': product_link,
                            'Specs': json.dumps(specs, ensure_ascii=False),
                            'Description': description
                        }

                        scraped_laptops.append(laptop_product)

                        # Log successful scrape
                        logger.info(f"Scraped: {name}")

                    except Exception as product_error:
                        logger.error(f"Error scraping individual product: {product_error}")

                # Pause to avoid rate limiting
                import time
                time.sleep(2)

            except requests.RequestException as e:
                logger.error(f"Error scraping page {page}: {e}")
                break

        logger.info(f"Total laptops scraped: {len(scraped_laptops)}")
        return scraped_laptops

def main():
    try:
        # Updated 2B laptops URL with the provided parameter
        search_url = 'https://2b.com.eg/ar/computers/laptops.html?_=1733227040653'

        # Initialize scraper
        scraper = LaptopScraper(search_url)

        # Scrape laptop data
        scraped_laptops = scraper.scrape_laptop_data(max_pages=3)

        # Convert scraped data to DataFrame
        df = pd.DataFrame(scraped_laptops)

        # Save DataFrame to Excel file
        df.to_excel('scraped_laptops.xlsx', index=False, encoding='utf-8')

        logger.info("Data has been written to 'scraped_laptops.xlsx' successfully.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
