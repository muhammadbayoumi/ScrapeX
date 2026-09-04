# منظومة أدوات Scraping المفتوحة المصدر

> **RESEARCH.** This is the platform ScrapeX already is — `sources.yaml`, the
> connector family registry, the fetchers, the politeness budget, the scheduler,
> snapshot storage and provenance. Read it as a checklist against the code, not
> as a shopping list. The Scraper Registry app is an issue in milestone **#10**.

## الخلاصة

لا توجد أداة واحدة هي الأفضل لكل المصادر. الأنسب هو Apps مستقلة بعقد بيانات واحد: API/feed، جلب HTTP، متصفح ديناميكي، مستندات/OCR، ومراقبة تغييرات. بعد فحص الـcrawler الموجود نحدد ما نعيد استخدامه.

## الملفات

| # | النقطة |
|---:|---|
| 01 | [اختيار المصدر: API أولًا](01-source-selection-api-first.md) |
| 02 | [الصفحات الثابتة وHTTP](02-static-http.md) |
| 03 | [JavaScript والمتصفح](03-dynamic-browser.md) |
| 04 | [الزحف والاكتشاف](04-crawling-discovery.md) |
| 05 | [الاستخراج المنظم](05-structured-extraction.md) |
| 06 | [استخراج النص وLLM](06-text-llm-extraction.md) |
| 07 | [الأدوات المرئية وNo-code](07-visual-no-code.md) |
| 08 | [PDF والمرفقات وOCR](08-documents-pdf-ocr.md) |
| 09 | [الجلسات والنماذج وتسجيل الدخول](09-auth-sessions-forms.md) |
| 10 | [مراقبة التغييرات](10-change-detection.md) |
| 11 | [الجدولة والطوابير والتوسع](11-scheduling-queues-scale.md) |
| 12 | [التخزين وإزالة التكرار والمصدر](12-storage-dedup-provenance.md) |
| 13 | [الموثوقية والمراقبة والأمان](13-reliability-observability-security.md) |
| 14 | [القانون والأخلاق واللطف](14-legal-ethical-politeness.md) |

## خريطة الأدوات

| المشروع | يغطي | ملاحظة |
|---|---|---|
| [Scrapy](https://github.com/scrapy/scrapy) | crawler وselectors وpipelines | Python، BSD-3-Clause |
| [Crawlee](https://github.com/apify/crawlee) | HTTP/browser/queues/sessions | JS/TS، Apache-2.0 |
| [Playwright](https://github.com/microsoft/playwright) | متصفح ديناميكي | Apache-2.0؛ استخدمه عند الضرورة |
| [Selenium](https://github.com/SeleniumHQ/selenium) / [Puppeteer](https://github.com/puppeteer/puppeteer) | بدائل browser automation | حسب لغة المنظومة |
| [Colly](https://github.com/gocolly/colly) | crawler سريع | Go |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Markdown/JSON وLLM-ready | حدّثه واعزل خدمته |
| [Firecrawl](https://github.com/firecrawl/firecrawl) | scrape/crawl API | راجع AGPL وفروق السحابة عن self-hosting |
| [Crawlab](https://github.com/crawlab-team/crawlab) | إدارة spiders | لوحة تشغيل، BSD-3-Clause |
| [Scrapyd](https://github.com/scrapy/scrapyd) | نشر Scrapy | خدمة تشغيل وليست extractor |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) / [urlwatch](https://github.com/thp/urlwatch) | تغيرات وتنبيهات | ممتازان للـwatch lists |
| [Huginn](https://github.com/huginn/huginn) | workflows وagents | تكامل مرن |
| [extruct](https://github.com/scrapinghub/extruct) / [Trafilatura](https://github.com/adbar/trafilatura) | بيانات منظمة/نص نظيف | مرحلة استخراج |
| [Apache Tika](https://tika.apache.org/) / [Tesseract](https://github.com/tesseract-ocr/tesseract) | مستندات وOCR | workers معزولة |
| [ArchiveBox](https://github.com/ArchiveBox/ArchiveBox) | حفظ أدلة | وفق الحقوق وسياسة الاحتفاظ |

## الشكل العام

```text
Source Registry
 ├─ API/Feed Adapter
 ├─ Static Fetcher
 ├─ Browser Fetcher
 ├─ Document Extractor
 └─ Change Watcher
        ↓
Extractor Registry → Normalizer/Validator → Evidence Store → Domain Apps
```

الأولوية: API/feed ثم JSON-LD أو HTML ثابت، ثم المتصفح، ثم OCR/LLM عند الحاجة. تكلفة وهشاشة المتصفح وOCR وLLM أعلى من HTTP.

لا تجاوز لـCAPTCHA أو الحجب أو تسجيل الدخول. راجع robots.txt والشروط والتراخيص والخصوصية؛ الاستخدام الشخصي لا يلغيها.
