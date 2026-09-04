# 02 — السعر الحالي والعرض

## الحقول

المبلغ، العملة، نوع السعر (`regular/sale/member/from/installment`)، السعر السابق، فترة الصلاحية، seller، الحالة، الكمية والوقت.

## ترتيب الاستخراج

1. API أو product feed رسمي.
2. JSON-LD من [Schema.org Offer](https://schema.org/Offer) عبر [extruct](https://github.com/scrapinghub/extruct).
3. عناصر HTML محددة بـCSS/XPath.
4. متصفح آلي إذا كان السعر ينتج بعد JavaScript.
5. OCR للصورة كحل أخير وثقة منخفضة.

[price-parser](https://github.com/scrapinghub/price-parser) ينظف نصوص المبلغ والعملات، لكنه لا يعرف معنى الرقم أو سياقه.

## التحقق

- المبلغ موجب ومعقول للعملة والفئة.
- السعر داخل عنصر العرض المطلوب لا «منتجات مشابهة».
- العملة صريحة أو مثبتة من market context.
- السعر ليس قسطًا شهريًا أو قيمة توفير أو `from` مخفيًا.

## نتيجة مقترحة

`amount_decimal`, `currency_iso`, `price_type`, `valid_from/to`, `evidence_selector/json_path`, `raw_text`, `observed_at`, `confidence`.

