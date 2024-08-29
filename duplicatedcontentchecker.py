import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import hashlib
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ContentDuplicateChecker:
    def __init__(self, base_url, max_depth=2):
        self.base_url = base_url
        self.max_depth = max_depth
        self.visited_urls = set()
        self.content_hashes = {}
        self.content_texts = {}
        self.similarity_scores = []

    def crawl(self, url, depth=0):
        logging.info(f'Crawling URL: {url} at depth: {depth}')
        if depth > self.max_depth or url in self.visited_urls:
            return
        self.visited_urls.add(url)

        try:
            response = requests.get(url)
            if response.status_code != 200:
                logging.warning(f'Failed to retrieve {url}, status code: {response.status_code}')
                return
            soup = BeautifulSoup(response.content, 'html.parser')
            page_content = self.extract_content(soup)
            if page_content:
                content_hash = hashlib.md5(page_content.encode('utf-8')).hexdigest()
                self.content_hashes[url] = content_hash
                self.content_texts[url] = page_content
                logging.info(f'Extracted content from {url}')
            else:
                logging.warning(f'No content extracted from {url}')

            # Find all internal links and crawl them
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                full_url = urljoin(url, href)
                if self.is_internal_link(full_url):
                    self.crawl(full_url, depth + 1)
        except Exception as e:
            logging.error(f"Failed to crawl {url}: {e}")
    def extract_content(self, soup):
        for script in soup(["script", "style"]):
            script.decompose()  # Remove all script and style elements
        content = ' '.join(soup.stripped_strings)
        logging.debug(f'Extracted content: {content[:500]}...')  # Log first 500 characters
        return content

    def is_internal_link(self, url):
        return urlparse(url).netloc == urlparse(self.base_url).netloc

    def compare_contents(self):
        urls = list(self.content_texts.keys())
        if not urls:
            logging.warning('No content available for comparison.')
            return
        vectorizer = CountVectorizer().fit_transform(self.content_texts.values())
        vectors = vectorizer.toarray()
        csim = cosine_similarity(vectors)
        for i in range(len(urls)):
            for j in range(i + 1, len(urls)):
                if csim[i, j] > 0.7:  # Threshold for considering as duplicate
                    self.similarity_scores.append((urls[i], urls[j], csim[i, j]))
                    logging.info(f'Found similar content between {urls[i]} and {urls[j]} with similarity {csim[i, j]:.2f}')

    def generate_report(self, output_path='duplicate_report.csv'):
        if not self.similarity_scores:
            logging.info('No similar content found.')
        df = pd.DataFrame(self.similarity_scores, columns=['URL_1', 'URL_2', 'Similarity'])
        df.to_csv(output_path, index=False)
        logging.info(f'Report generated: {output_path}')

    def run(self):
        self.crawl(self.base_url)
        self.compare_contents()
        self.generate_report()

# Example usage:
# checker = ContentDuplicateChecker(base_url="https://example.com", max_depth=2)
# checker.run()
