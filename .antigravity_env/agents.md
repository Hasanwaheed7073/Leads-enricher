# Multi-Agent Architecture for Lead Sniper
We are building an autonomous Lead Research Engine. The system operates via the following logical agents:
- AGENT 1 (Ingestor): Reads CSV data (Name, Email, URL, LinkedIn) and sanitizes inputs.
- AGENT 2 (Scout): Uses zero-cost scraping (e.g., BeautifulSoup/Puppeteer) on the provided Website URLs to extract the "About Us" and "Services" text.
- AGENT 3 (Scorer & Pitcher): Analyzes the scraped data against the CSV context to score the lead (1-10) and generate a highly personalized 3-sentence outreach pitch.
