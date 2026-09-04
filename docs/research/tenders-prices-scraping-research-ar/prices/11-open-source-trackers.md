# 11 — مشروعات وأدوات تتبّع الأسعار المفتوحة

| المشروع | أنسب استخدام | ما لا يفعله وحده |
|---|---|---|
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | مراقبة رابط، price/restock، history، notifications وAPI | لا يبني كتالوج منتجات موحدًا تلقائيًا |
| [urlwatch](https://github.com/thp/urlwatch) | مراقبة جزء من HTML أو JSON وإرسال diff | يحتاج filters وإدارة خارجية للقوائم |
| [Huginn](https://github.com/huginn/huginn) | workflows للجلب والتحويل والجدولة والتنبيه | إعداد أثقل من متعقب سعر مباشر |
| Scrapy أو Crawlee | زحف كتالوجات كثيرة باستخراج مخصص | يحتاج تطويرًا وصيانة للمصادر |
| Playwright | صفحات JavaScript واختيار سوق/فرع | مكلف وبطيء مقارنة بـHTTP |
| [extruct](https://github.com/scrapinghub/extruct) | استخراج JSON-LD/microdata للمنتج والعرض | لا يجلب الصفحة ولا يتحقق من حداثتها |
| [price-parser](https://github.com/scrapinghub/price-parser) | تحليل مبلغ وعملة من النص | لا يفهم شروط العرض أو الشحن |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | مرشح لمطابقة أسماء المنتجات | لا يستبدل GTIN/MPN والتحقق اليدوي |

## تصميم عملي متعدد التطبيقات

1. **Quick Watch:** changedetection.io/urlwatch للروابط المهمة والتنبيه السريع.
2. **Catalog Tracker:** Scrapy أو Crawlee للتاريخ المنظم والمنتجات الكثيرة.
3. **Dynamic Fetcher:** Playwright فقط للمصادر التي لا تعمل دون متصفح.
4. **Normalizer:** extruct + price-parser + قواعد الهوية وسعر الوحدة.

بهذا نستفيد من قوة كل مشروع بدل محاولة تحويل أداة واحدة إلى كل شيء. قبل الدمج نراجع الإصدار والترخيص فعليًا ونثبت النسخة المستخدمة.

