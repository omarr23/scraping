import requests
from bs4 import BeautifulSoup
import mariadb
import sys
import re
import logging
import json
from fake_useragent import UserAgent
from rapidfuzz import fuzz  # Import rapidfuzz for fuzzy matching

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AmazonCPUScraper:
    def __init__(self, search_url, database_connection):
        """
        Initialize the Amazon CPU scraper

        Args:
            search_url (str): Amazon search URL for CPUs
            database_connection: Active database connection
        """
        self.url = search_url
        self.conn = database_connection
        self.cursor = database_connection.cursor(dictionary=True)
        self.ua = UserAgent()

    def extract_specifications(self, description):
        """
        Extract key specifications from product description

        Args:
            description (str): Product description text

        Returns:
            dict: Extracted specifications
        """
        specs = {}

        # Regex patterns for common CPU specifications
        spec_patterns = [
            (r'(\d+)\s*Cores?', 'Cores'),
            (r'(\d+)\s*Threads?', 'Threads'),
            (r'(\d+(?:\.\d+)?)\s*GHz\s*Base', 'Base Clock'),
            (r'(\d+(?:\.\d+)?)\s*GHz\s*Boost', 'Boost Clock'),
            (r'(Ryzen\s*\d+|Core\s*i\d+)', 'Series'),
        ]

        for pattern, key in spec_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                specs[key] = match.group(1)

        return specs

    def scrape_cpu_data(self, max_pages=3):
        """
        Scrape CPU data from Amazon search results

        Args:
            max_pages (int): Maximum number of pages to scrape

        Returns:
            list: Scraped CPU products
        """
        scraped_cpus = []

        for page in range(1, max_pages + 1):
            try:
                # Prepare request headers
                headers = {
                    'User-Agent': self.ua.random,
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Pragma': 'no-cache',
                    'Cache-Control': 'no-cache'
                }

                # Modify URL for pagination
                paginated_url = f"{self.url}&page={page}"

                # Send request
                response = requests.get(paginated_url, headers=headers)
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')

                # Find CPU product containers
                product_containers = soup.find_all('div', {'data-component-type': 's-search-result'})

                for container in product_containers:
                    try:
                        # Extract product name
                        name_elem = container.find('h2', {'class': 'a-size-mini'})
                        if not name_elem:
                            continue

                        name = name_elem.text.strip()

                        # Extract price
                        price_whole = container.find('span', {'class': 'a-price-whole'})
                        price_fraction = container.find('span', {'class': 'a-price-fraction'})
                        if price_whole and price_fraction:
                            price = f"{price_whole.text.strip()}.{price_fraction.text.strip()}"
                        elif price_whole:
                            price = price_whole.text.strip()
                        else:
                            price = 'N/A'

                        # Extract product link
                        link_elem = container.find('a', {'class': 'a-link-normal'})
                        if not link_elem:
                            continue

                        product_link = 'https://www.amazon.com' + link_elem['href']

                        # Fetch product page for more details
                        product_page = requests.get(product_link, headers=headers)
                        product_soup = BeautifulSoup(product_page.content, 'html.parser')

                        # Extract product description
                        description_elem = product_soup.find('div', {'id': 'productDescription'})
                        if description_elem:
                            description = description_elem.text.strip()
                        else:
                            # Alternative description extraction
                            description_elem = product_soup.find('meta', {'name': 'description'})
                            description = description_elem['content'].strip() if description_elem else ''

                        # Extract specifications
                        specs = self.extract_specifications(description)

                        # Create product entry
                        cpu_product = {
                            'name': name,
                            'price': price,
                            'link': product_link,
                            'specs': specs,
                            'description': description
                        }

                        scraped_cpus.append(cpu_product)

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

        logger.info(f"Total CPUs scraped: {len(scraped_cpus)}")
        return scraped_cpus

class ProductMatcher:
    def __init__(self, database_connection):
        """
        Initialize product matcher

        Args:
            database_connection: Active database connection
        """
        self.conn = database_connection
        self.cursor = database_connection.cursor(dictionary=True)

    def normalize_text(self, text):
        """
        Normalize text for comparison

        Args:
            text (str): Input text to normalize

        Returns:
            str: Normalized text
        """
        if not text:
            return ""
        # Remove non-alphanumeric characters and convert to lowercase
        return re.sub(r'\W+', ' ', str(text).lower().strip())

    def calculate_spec_similarity(self, scraped_specs, db_specs):
        """
        Calculate similarity between scraped and database specifications

        Args:
            scraped_specs (dict): Scraped product specifications
            db_specs (dict): Database product specifications

        Returns:
            float: Specification similarity score (0-100)
        """
        if not scraped_specs or not db_specs:
            return 0

        match_scores = []
        for key, scraped_value in scraped_specs.items():
            normalized_key = self.normalize_text(key)
            normalized_scraped_value = self.normalize_text(scraped_value)

            best_match_score = 0
            for db_key, db_value in db_specs.items():
                normalized_db_key = self.normalize_text(db_key)
                normalized_db_value = self.normalize_text(db_value)

                # Check if the specification keys are similar
                key_similarity = fuzz.token_set_ratio(normalized_key, normalized_db_key)
                if key_similarity > 80:  # Threshold for key similarity
                    # Calculate value similarity
                    value_similarity = fuzz.token_set_ratio(normalized_scraped_value, normalized_db_value)
                    best_match_score = max(best_match_score, value_similarity)
            match_scores.append(best_match_score)

        # Average the match scores
        spec_similarity = sum(match_scores) / len(match_scores) if match_scores else 0
        return spec_similarity

    def calculate_price_similarity(self, scraped_price, db_price):
        """
        Calculate similarity between scraped and database prices

        Args:
            scraped_price (str): Scraped product price
            db_price (str): Database product price

        Returns:
            float: Price similarity score (0-100)
        """
        try:
            scraped_price = float(re.sub(r'[^\d.]', '', str(scraped_price)))
            db_price = float(re.sub(r'[^\d.]', '', str(db_price)))
            price_difference_percentage = abs(scraped_price - db_price) / (db_price or 1) * 100
            price_similarity = max(0, 100 - price_difference_percentage)
            return price_similarity
        except (ValueError, TypeError):
            return 0

    def calculate_similarity_score(self, scraped_product, db_product):
        """
        Calculate similarity score between scraped and database products

        Args:
            scraped_product (dict): Product details from web scraping
            db_product (dict): Product details from database

        Returns:
            float: Similarity score (0-100)
        """
        # Normalize names
        scraped_name = self.normalize_text(scraped_product['name'])
        db_name = self.normalize_text(db_product['name'])

        # Use rapidfuzz for name similarity
        name_similarity = fuzz.token_set_ratio(scraped_name, db_name)

        # Specification similarity
        scraped_specs = scraped_product.get('specs', {})
        db_specs = json.loads(db_product.get('specs', '{}')) if db_product.get('specs') else {}
        spec_similarity = self.calculate_spec_similarity(scraped_specs, db_specs)

        # Price similarity
        price_similarity = self.calculate_price_similarity(scraped_product.get('price'), db_product.get('price'))

        # Weighted similarity calculation
        total_score = (
            name_similarity * 0.5 +   # Name matching is crucial
            spec_similarity * 0.3 +   # Specifications are important
            price_similarity * 0.2    # Price similarity is a bonus
        )

        return total_score

    def find_best_match(self, scraped_product, similarity_threshold=70):
        """
        Find the best matching product in the database

        Args:
            scraped_product (dict): Product details from web scraping
            similarity_threshold (float): Minimum similarity score to consider a match

        Returns:
            dict or None: Best matching product or None
        """
        try:
            # Query all products from database
            self.cursor.execute("SELECT * FROM AMD_Processors")
            all_products = self.cursor.fetchall()

            # Calculate similarity for each product
            matches = []
            for db_product in all_products:
                similarity_score = self.calculate_similarity_score(scraped_product, db_product)
                if similarity_score >= similarity_threshold:
                    matches.append({
                        'product': db_product,
                        'score': similarity_score
                    })

            # Sort matches by similarity score in descending order
            matches.sort(key=lambda x: x['score'], reverse=True)

            if matches:
                best_match = matches[0]['product']
                best_match['similarity_score'] = matches[0]['score']
                return best_match
            else:
                return None

        except Exception as e:
            logger.error(f"Error in finding best match: {e}")
            return None

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
        logger.info("Database connection successful!")
        return conn
    except mariadb.Error as e:
        logger.error(f"Error connecting to MariaDB: {e}")
        sys.exit(1)

def main():
    # Establish database connection
    conn = connect_to_database()

    try:
        # Amazon search URL for CPUs (replace with your specific search)
        search_url = 'https://www.amazon.com/s?k=AMD+Ryzen+Processor'

        # Initialize scraper and matcher
        scraper = AmazonCPUScraper(search_url, conn)
        matcher = ProductMatcher(conn)

        # Scrape CPU data
        scraped_cpus = scraper.scrape_cpu_data(max_pages=3)

        # Match each scraped CPU
        matched_products = []
        for cpu in scraped_cpus:
            best_match = matcher.find_best_match(cpu)

            if best_match:
                similarity_score = best_match['similarity_score']
                logger.info(
                    f"Matched: {cpu['name']} -> {best_match['name']} "
                    f"(Total Score: {similarity_score:.2f}%)"
                )
                matched_products.append({
                    'scraped_product': cpu,
                    'database_match': best_match,
                    'similarity_score': similarity_score
                })
            else:
                logger.warning(f"No match found for: {cpu['name']}")

        # Save results to a JSON file
        with open('amazon_cpu_matches.json', 'w') as f:
            json.dump(matched_products, f, indent=2)

        return matched_products

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always close the database connection
        conn.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    main()
