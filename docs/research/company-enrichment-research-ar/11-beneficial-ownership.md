# 11 — الملكية والمستفيد الحقيقي

## الفرق

- **الملكية القانونية:** من يملك الأسهم أو الكيان مباشرة.
- **المستفيد الحقيقي:** الشخص الطبيعي الذي يملك أو يسيطر في النهاية وفق تعريف القانون المحلي.
- **السيطرة:** قد تأتي من التصويت أو اتفاق أو منصب، لا من نسبة الأسهم فقط.

## مصادر ومعايير

- [Beneficial Ownership Data Standard (BODS)](https://standard.openownership.org/en/main/): معيار مفتوح لتمثيل الكيانات والأشخاص والملكية المؤرخة.
- [Open Ownership BODS data](https://bods-data.openownership.org/): أمثلة وبيانات منشورة من جهات مشاركة.
- [Companies House PSC API](https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/persons-with-significant-control) للمملكة المتحدة.
- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api) للعلاقات المباشرة والنهائية المبلغ عنها للكيانات ذات LEI.
- [OpenCorporates](https://api.opencorporates.com/documentation/API-Reference) و[OpenSanctions](https://www.opensanctions.org/docs/) قد يعرضان علاقات مستمدة من مصادر أخرى.
- أدوات [BODS analysis](https://github.com/openownership/bodsanalysis) مفتوحة MIT للتحليل.

## نتيجة مقترحة

علاقة مؤرخة: `subject`, `interested_party`, نوع المصلحة، نسبة مباشرة/غير مباشرة إن نشرت، وسائل السيطرة، الحالة، والمصدر.

## حدود حرجة

غياب اسم مستفيد لا يعني عدم وجوده؛ قد يكون غير منشور أو مستثنى أو عبر سلسلة معقدة. لا تحسب المستفيد النهائي آليًا دون توضيح الافتراضات، ولا تعرض ادعاءًا حساسًا بلا رابط وسياق زمني.

**يغطي أيضًا:** الشركة الأم، العقوبات، تضارب المصالح، والمخاطر.

