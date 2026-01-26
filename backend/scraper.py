from playwright.async_api import async_playwright
import asyncio

class HolyGrailScraper:
    def __init__(self, category, subject, year=None, documentType="Exam Papers", pages=5):
        self.category = category
        self.subject = subject
        self.documentType = documentType
        self.year = year
        self.pages = pages
    async def get_documents(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(f"https://grail.moe/library", timeout=60000)
            
            # apply filters 
            filters = [self.category, self.subject, self.year, self.documentType]
            
            for i, option_name in enumerate(filters):
                if option_name:  
                    input_box = page.locator('input[role="combobox"]').nth(i)
                    await input_box.fill(option_name)
                    await asyncio.sleep(0.5)

                    await page.get_by_role("option", name=option_name).click()
                    await input_box.wait_for(state="visible") # it somehow only selects second field correctly with this line but if it works it works
                    await asyncio.sleep(0.5)

            for i in range(1,self.pages+1):  # get links for each page 
                pdf_links = await page.locator('a[href^="https://document.grail.moe/"][href$=".pdf"]').all()
               
                print(f"Page {i}:")
                for link in pdf_links:
                    href = await link.get_attribute("href")
                    print(href)

                if i == self.pages:
                    break

                await page.get_by_role("button", name="Next").click()

                await page.wait_for_url(
                    lambda url: f"page={i+1}" in url,
                    timeout=10000
                )

            await browser.close()

if __name__ == "__main__":
    scraper = HolyGrailScraper("GCE 'A' Levels", "H2 Economics", None, "Exam Papers")
    asyncio.run(scraper.get_documents())