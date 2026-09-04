# 16 — القوائم والنتائج المالية

## الحقول

الإيراد، الربح/الخسارة، الأصول، الخصوم، النقد، التدفقات، العملة، الفترة، نوع القوائم، والمدقق. يجب حفظ السياق المحاسبي؛ الرقم بلا فترة أو عملة غير صالح.

## المصادر والأدوات

- [SEC Company Facts/XBRL APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) وإيداعات EDGAR للشركات الأمريكية المبلغة.
- حسابات [Companies House](https://www.gov.uk/government/organisations/companies-house/about/about-our-services) المتاحة بصيغ HTML/iXBRL أو ملفات.
- [Arelle](https://github.com/Arelle/Arelle): معالج XBRL مفتوح Apache-2.0 بواجهات CLI/Python/API.
- تقارير المستثمرين بالموقع الرسمي، مع الرجوع إلى الملف الأصلي.

## النموذج الصحيح

لكل fact: `concept`, `value`, `unit`, `period_start/end` أو `instant`, `entity_scope`, `statement`, `filing_id`, `source_url`. لا تضع «الإيراد الأخير» كقيمة ثابتة بلا هذه الأبعاد.

## حدود

- الشركات الخاصة والدول غير الناشرة قد لا تتوافر لها بيانات.
- اختلاف المعايير والعملات والسنة المالية يجعل المقارنة المباشرة مضللة.
- إعادة صياغة القوائم تعني أن أحدث إيداع قد يعدّل أرقام سنوات سابقة.
- OCR من PDF أقل ثقة من XBRL ويحتاج مراجعة.

**يغطي أيضًا:** الحجم، الصحة المالية، التمويل، والسوق العام.

