# 05 — المخزون والتوفر والتوصيل

## الحالات

`in_stock`, `out_of_stock`, `preorder`, `backorder`, `limited`, `store_only`, `discontinued`, `unknown`. لا تجعل زر «أضف للسلة» الدليل الوحيد.

## المصادر

- `availability` في [Schema.org Offer](https://schema.org/Offer).
- نص وحالة الزر وvariant المحدد.
- API/feed رسمي.
- changedetection.io يملك نمط restock مناسبًا للتنبيه.

## سياق التوصيل

قد يكون المنتج متوفرًا عامة وغير قابل للتوصيل لرمز بريدي معين، أو متوفرًا في فرع فقط. خزّن `delivery_country/postal_code`, store ID، earliest date والوقت.

## النتيجة

حالة معيارية + النص الأصلي + سبب الاستنتاج + المنطقة + `observed_at`. حدث `restocked` يتطلب انتقالًا من حالة عدم التوفر إلى التوفر، وليس مجرد نجاح جلب الصفحة.

## حدود

المخزون سريع التغير وقد يكون cached. لا تختبر checkout أو تحجز وحدات آليًا؛ ذلك يغيّر حالة خارجية. إذا احتاج إثبات التوفر إضافة للسلة، يتطلب قرارًا منفصلًا وآلية لا تنفذ الطلب.

