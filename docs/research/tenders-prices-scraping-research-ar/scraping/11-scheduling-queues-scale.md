# 11 — الجدولة والطوابير والتوسع

تفصل الطوابير بين discovery وfetch وextract وdocument وbrowser jobs. لكل job معرّف idempotency ومحاولات محدودة وسبب فشل واضح. تستخدم retry/backoff للأخطاء المؤقتة فقط، ثم dead-letter queue للمراجعة.

[Scrapyd](https://github.com/scrapy/scrapyd) ينشر ويشغّل Scrapy spiders، و[Crawlab](https://github.com/crawlab-team/crawlab) يوفر إدارة متعددة الأطر، بينما Scrapy/Crawlee يديران queues داخل محرك الزحف.

## ضوابط التشغيل

- جدولة حسب TTL وأهمية المصدر، لا تردد واحد للجميع.
- concurrency وrate limit لكل domain وcredential.
- workers منفصلة لـHTTP والمتصفح وOCR.
- قفل يمنع تشغيل نسختين متزامنتين للمصدر نفسه.
- ميزانية يومية للطلبات والمتصفح والتخزين وLLM.

التوسع يبدأ بعد قياس success rate وyield والتكلفة. للاستخدام الشخصي غالبًا تكفي عملية واحدة وطابور صغير؛ لا حاجة لبنية موزعة مبكرًا.

