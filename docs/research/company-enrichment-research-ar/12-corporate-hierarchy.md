# 12 — الشركة الأم والفروع والمجموعة

## العلاقات

شركة أم مباشرة ونهائية، شركات تابعة، فروع قانونية، علامات ومنتجات، مشاريع مشتركة، واستحواذات تاريخية. يجب عدم مساواة «علامة تجارية» بـ«شركة تابعة» تلقائيًا.

## المصادر

- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api): علاقات الأم المباشرة والنهائية وبيانات الفروع الدولية في نطاق LEI.
- السجلات الوطنية و[OpenCorporates](https://api.opencorporates.com/documentation/API-Reference): فروع، home company، controlling entities حيث تتوافر.
- [Companies House PSC](https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/persons-with-significant-control) و[BODS](https://standard.openownership.org/en/main/).
- [SEC EDGAR](https://www.sec.gov/search-filings): قوائم الشركات التابعة والإفصاحات والاستحواذات.
- [Wikidata](https://www.wikidata.org/wiki/Help:Data_access) و[OpenSanctions](https://www.opensanctions.org/docs/) للاكتشاف والتحقق المتقاطع.

## النموذج

استخدم رسمًا بيانيًا لعلاقات مؤرخة: `parent_of`, `subsidiary_of`, `branch_of`, `brand_of`, `acquired_by`, `joint_venture_with`. لكل حافة مصدر وثقة وفترة.

## حدود

الهيكل يتغير بالاستحواذات وإعادة التنظيم. وجود نفس النطاق أو المدير لا يثبت الملكية. وغياب علاقة في GLEIF قد يكون بسبب استثناء إبلاغ؛ احتفظ بسبب الاستثناء إن نشر.

**يغطي أيضًا:** الملكية، الهوية، البيانات المالية المجمعة، والعقوبات المشتقة عبر المجموعة.

