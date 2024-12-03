import requests
from bs4 import BeautifulSoup
import mariadb
import sys
import re
import logging
import json
from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LaptopScraper:
    def __init__(self, search_url, database_connection):
        """
        Initialize the Laptop scraper with improved Arabic support

        Args:
            search_url (str): URL for laptops
            database_connection: Active database connection
        """
        self.url = search_url
        self.conn = database_connection
        self.cursor = database_connection.cursor()
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
        
        # Normalize Arabic characters
        text = text.replace('٠', '0').replace('١', '1').replace('٢', '2') \
                   .replace('٣', '3').replace('٤', '4').replace('٥', '5') \
                   .replace('٦', '6').replace('٧', '7').replace('٨', '8') \
                   .replace('٩', '9')
        
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
            (r'(\d+)\s*جيجابايت\s*ذاكرة', 'RAM'),
            (r'(\d+)\s*جيجابايت\s*SSD', 'SSD'),
            (r'(\d+)\s*تيرابايت\s*HDD', 'HDD'),
            (r'(إنتل|AMD)\s+(كور|رايزن)\s*(\w+)', 'Processor'),
            (r'(\d+(?:\.\d+)?)\s*بوصة', 'Screen Size'),
            (r'(ويندوز|لينكس|ماك\s*أو\s*إس)', 'Operating System'),
        ]

        # Additional English patterns
        english_patterns = [
            (r'(\d+)\s*GB\s*RAM', 'RAM'),
            (r'(\d+)\s*GB\s*SSD', 'SSD'),
            (r'(\d+)\s*TB\s*HDD', 'HDD'),
            (r'(Intel|AMD)\s+(Core|Ryzen)\s*(\w+)', 'Processor'),
            (r'(\d+(?:\.\d+)?)\s*inch', 'Screen Size'),
            (r'(Windows|Linux|MacOS)', 'Operating System'),
        ]

        # Try Arabic patterns first
        for pattern, key in spec_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                specs[key] = match.group(1)
                break

        # If no Arabic match, try English patterns
        if not specs:
            for pattern, key in english_patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    specs[key] = match.group(1)
                    break

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
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
                }

                # Modify URL for pagination
                paginated_url = f"{self.url}?page={page}"

                # Send request with timeout
                response = requests.get(paginated_url, headers=headers, timeout=15)
                response.encoding = 'utf-8'  # Explicitly set UTF-8 encoding
                response.raise_for_status()

                # Parse HTML with UTF-8 support
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')

                # Find laptop product containers (adjust selectors as needed)
                product_containers = soup.find_all('div', class_=re.compile(r'product.*item'))

                if not product_containers:
                    logger.warning(f"No product containers found on page {page}")
                    continue

                for container in product_containers:
                    try:
                        # Extract product name (with Arabic support)
                        name_elem = container.find(['h2', 'div'], class_=re.compile(r'product.*title'))
                        if not name_elem:
                            continue

                        name = self.clean_text(name_elem.get_text(strip=True))

                        # Extract price
                        price_elem = container.find(['span', 'div'], class_=re.compile(r'price'))
                        price = self.clean_text(price_elem.get_text(strip=True)) if price_elem else 'N/A'

                        # Extract product link
                        link_elem = container.find('a', class_=re.compile(r'product.*link'))
                        if not link_elem:
                            continue

                        # Ensure full URL
                        product_link = (link_elem['href'] if link_elem['href'].startswith('http') 
                                        else 'https://2b.com.eg' + link_elem['href'])

                        # Fetch product page for more details
                        product_page = requests.get(product_link, headers=headers, timeout=15)
                        product_page.encoding = 'utf-8'
                        product_soup = BeautifulSoup(product_page.content, 'html.parser', from_encoding='utf-8')

                        # Extract product description
                        description_elem = product_soup.find(['div', 'p'], class_=re.compile(r'product.*description'))
                        description = self.clean_text(description_elem.get_text(strip=True)) if description_elem else 'No description available'

                        # Extract specifications
                        specs = self.extract_specifications(description)

                        # Create product entry
                        laptop_product = {
                            'name': name,
                            'price': price,
                            'link': product_link,
                            'specs': specs,
                            'description': description
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

    def insert_laptops_to_db(self, laptops):
        """
        Insert scraped laptops into the database with UTF-8 support

        Args:
            laptops (list): List of laptop dictionaries
        """
        for laptop in laptops:
            try:
                # Check if the laptop already exists in the database
                query = "SELECT COUNT(*) FROM laptops WHERE name = ?"
                self.cursor.execute(query, (laptop['name'],))
                result = self.cursor.fetchone()

                if result[0] > 0:
                    logger.info(f"Laptop already exists in the database: {laptop['name']}")
                    continue

                # Insert new laptop into the database with UTF-8 charset
                insert_query = """
                INSERT INTO laptops (name, price, link, specs, description)
                VALUES (?, ?, ?, ?, ?)
                """
                self.cursor.execute(insert_query, (
                    laptop['name'],
                    laptop['price'],
                    laptop['link'],
                    json.dumps(laptop['specs'], ensure_ascii=False),
                    laptop['description']
                ))
                self.conn.commit()
                logger.info(f"Inserted into database: {laptop['name']}")

            except mariadb.Error as db_error:
                logger.error(f"Error inserting laptop into database: {db_error}")

def connect_to_database():
    """
    Establish a connection to the MariaDB database

    Returns:
        mariadb.connection: Database connection
    """
    try:
        conn = mariadb.connect(
            user="root",
            password="",  # Replace with your actual password
            host="127.0.0.1",
            port=3306,
            database="processors"
        )
        
        # Execute SET NAMES to ensure UTF-8 support
        cursor = conn.cursor()
        cursor.execute("SET NAMES utf8mb4")
        cursor.execute("SET CHARACTER SET utf8mb4")
        cursor.execute("SET character_set_connection=utf8mb4")
        
        logger.info("Database connection successful!")
        return conn
    except mariadb.Error as e:
        logger.error(f"Error connecting to MariaDB: {e}")
        sys.exit(1)
def main():
    # Establish database connection
    conn = connect_to_database()

    try:
        # 2B laptops URL
        search_url = 'https://2b.com.eg/ar/computers/laptops.html'

        # Initialize scraper
        scraper = LaptopScraper(search_url, conn)

        # Scrape laptop data
        scraped_laptops = scraper.scrape_laptop_data(max_pages=3)

        # Insert laptops into the database
        scraper.insert_laptops_to_db(scraped_laptops)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always close the database connection
        conn.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    main()