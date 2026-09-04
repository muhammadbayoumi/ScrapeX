# 01 — هوية المنتج والمطابقة

## السؤال

هل عرضان يشيران إلى المنتج نفسه تمامًا؟ لا يمكن مقارنة iPhone بسعة مختلفة أو عبوتين بحجم مختلف لمجرد تشابه الاسم.

## ترتيب الأدلة

1. GTIN/EAN/UPC مطابق مع check digit صحيح.
2. Brand + manufacturer part number (MPN).
3. SKU، لكنه محلي لكل بائع.
4. model + variant attributes + pack size.
5. fuzzy title/image كمرشح للمراجعة فقط.

## مصادر وأدوات

- [Schema.org Product](https://schema.org/Product) يدعم GTIN وSKU وMPN وbrand وخصائص المنتج.
- [Open Food Facts](https://openfoodfacts.github.io/openfoodfacts-server/api/) للمنتجات الغذائية بالباركود.
- [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) لتشابه النص بعد التطبيع.
- Splink/dedupe من حزمة الشركات عند الحاجة لمطابقة سجلات واسعة.

## النموذج

افصل `product` عن `variant` وعن `offer`. العرض يحمل SKU البائع والرابط؛ النسخة تحمل اللون/الحجم/السعة/الكمية؛ المنتج يحمل العلامة والموديل العام.

## حدود

GTIN قد يكون مفقودًا أو خاطئًا في الصفحة، والmarketplace قد يعرض عدة variants تحت URL واحد. لا تدمج تلقائيًا إذا اختلفت خاصية مؤثرة أو حالة المنتج جديد/مستعمل/مجدّد.

