```markdown
# Content Duplicate Checker

## Overview

The **Content Duplicate Checker** is a Python-based tool designed to detect duplicate content across web pages within a specified domain. Duplicate content can significantly harm a website's SEO performance by confusing search engines and splitting ranking signals. This tool crawls a website, extracts content from multiple pages, compares the content using similarity metrics, and generates a detailed report highlighting pages with high similarity scores.

## Key Features

- **Website Crawling:** The tool crawls the specified domain, following internal links up to a user-defined depth.
- **Content Extraction:** Extracts textual content from each crawled page, filtering out scripts, styles, and other non-content elements.
- **Duplicate Detection:** Uses hashing and similarity metrics (e.g., Cosine Similarity) to detect both exact and near-duplicate content.
- **Detailed Reporting:** Generates a CSV report listing pairs of pages with high similarity scores, indicating potential duplicate content.

## How the Tool Works

### 1. Crawling
The tool begins by crawling the specified domain starting from the base URL. It identifies and follows internal links to explore pages up to a specified depth. The depth parameter allows control over how extensively the website is crawled.

### 2. Content Extraction
For each crawled page, the tool extracts the main textual content, stripping away unnecessary elements like scripts and styles. The extracted content is then processed and stored for comparison.

### 3. Content Comparison
The tool compares the content of all crawled pages using hashing and similarity metrics:
- **Hashing:** Quickly identifies exact duplicate content by generating and comparing content hashes.
- **Similarity Metrics:** Uses Cosine Similarity to detect near-duplicate content by comparing the vectorized representations of page content.

### 4. Report Generation
After the comparison, the tool generates a CSV report that lists pairs of URLs with high similarity scores, indicating potential duplicate content. The report includes:
- **URL_1 and URL_2:** The URLs of the compared pages.
- **Similarity:** The similarity score (ranging from 0 to 1) between the two pages' content.

## How to Use the Tool

### Installation

First, ensure you have Python installed. Then, install the required dependencies using pip:

```bash
pip install -r requirements.txt
```

### Running the Tool

To use the tool, create a Python script that initializes the `ContentDuplicateChecker` with your desired parameters and runs it:

```python
from duplicatedcontentchecker import ContentDuplicateChecker

checker = ContentDuplicateChecker(base_url="https://yourdomain.com", max_depth=4)
checker.run()
```

### Interpreting the Results

The tool generates a CSV report (`duplicate_report.csv`) with the following columns:

- **URL_1:** The first page's URL being compared.
- **URL_2:** The second page's URL being compared.
- **Similarity:** The similarity score between the two pages, ranging from 0 to 1.

#### Example Interpretation

- **Similarity Score 0.9 - 1.0:** These pages are almost identical in content, suggesting strong duplication. It is recommended to consolidate or differentiate the content to avoid SEO penalties.
- **Similarity Score 0.7 - 0.9:** These pages have significant similarities and might be considered near-duplicates. Consider reviewing and updating the content to enhance uniqueness.
- **Similarity Score below 0.7:** These pages have moderate to low similarity, which typically indicates that the content is sufficiently unique.

## Use Cases

- **SEO Audits:** Detect and mitigate duplicate content issues that could negatively impact search engine rankings.
- **Content Management:** Regularly monitor a website for unintentional content duplication, especially on large sites with many pages.
- **Competitor Analysis:** While primarily designed for use on your own website, the tool can also be adapted to analyze competitor sites for similar content strategies.

## Customization and Extensibility

The tool is designed to be extensible. Developers can customize the crawling behavior, content extraction logic, or similarity threshold to better fit specific use cases. For example:
- **Adjust the Similarity Threshold:** Modify the threshold for flagging content as duplicate in the `compare_contents` method.
- **Extend Content Extraction:** Customize the `extract_content` method to better handle complex or dynamic content.

## Limitations

- **Dynamic Content:** The tool may not fully capture content that is dynamically loaded via JavaScript, depending on the structure of the website.
- **Large Websites:** For very large websites, increasing the `max_depth` might result in long processing times or high memory usage.

## Conclusion

The **Content Duplicate Checker** is a valuable tool for maintaining the SEO health of a website by ensuring that content is unique and non-repetitive. By using this tool, you can proactively identify and address content duplication issues, helping to improve search engine rankings and user experience.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
```
