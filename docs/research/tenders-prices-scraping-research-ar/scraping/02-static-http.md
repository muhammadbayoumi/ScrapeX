# 02 — الصفحات الثابتة وHTTP

## الأدوات

[Scrapy](https://github.com/scrapy/scrapy) متكامل في Python للطلبات وselectors وpipelines وAutoThrottle. [Crawlee](https://github.com/apify/crawlee) يوفر HTTP مع queues وsessions وstorage في JavaScript/TypeScript، و[Colly](https://github.com/gocolly/colly) مناسب لخدمة Go خفيفة.

## سير العمل

يجلب الـfetcher الصفحة مع timeout وحجم أقصى، ويتحقق من نوع المحتوى والترميز، ثم يحفظ status وheaders ووقت الرصد وhash قبل تمريرها إلى extractor. تستخدم retries محدودة مع backoff للأخطاء المؤقتة، وتحترم `Retry-After`.

يُحدد التوازي ومعدل الطلبات لكل نطاق. نستخدم caching وETag وLast-Modified عندما يدعمها المصدر لتقليل الحمل.

إذا لم يظهر الحقل في الاستجابة الخام لكنه ظهر بعد JavaScript، نصعّد إلى browser fetcher. لا نفعل ذلك إن كان JSON-LD أو endpoint رسميًا متاحًا.
