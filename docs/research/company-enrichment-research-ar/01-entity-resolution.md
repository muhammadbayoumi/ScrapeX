# 01 — حلّ هوية الشركة وإزالة التكرار

## السؤال

هل السجلات التي تحمل أسماء متقاربة تشير إلى الشركة القانونية نفسها، أم إلى شركات مختلفة؟ هذه أهم خطوة؛ أي خطأ هنا يلوّث جميع الحقول اللاحقة.

## الأدلة المفيدة

- تطابق رقم التسجيل أو LEI/CIK: دليل قوي جدًا.
- تطابق النطاق الرسمي والهاتف والعنوان: مجموعة أدلة قوية.
- الاسم وحده: مرشح فقط، خصوصًا للأسماء العامة والفروع المحلية.
- البلد/الاختصاص والشكل القانوني والأسماء السابقة تساعد على الفصل.

## مصادر وأدوات مفتوحة

- [OpenRefine Reconciliation](https://openrefine.org/docs/manual/reconciling): مراجعة ومطابقة تفاعلية.
- [OpenCorporates Reconciliation API](https://api.opencorporates.com/documentation/Open-Refine-Reconciliation-API): مرشحون من سجلات الشركات.
- [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api): بحث كامل أو تقريبي بالاسم والعنوان وLEI.
- [Splink](https://github.com/moj-analytical-services/splink): ربط سجلات احتمالي واسع النطاق.
- [dedupe](https://github.com/dedupeio/dedupe): إزالة تكرار وحل كيانات بالتعلم النشط.
- [Wikidata](https://www.wikidata.org/wiki/Help:Data_access): معرّفات وأسماء بديلة، مع ضرورة التحقق.

## نتيجة مقترحة

`matched | possible_match | ambiguous | not_found` مع `candidate_ids` وأسباب النقاط ودرجة منفصلة لكل دليل.

## قواعد

- لا تدمج تلقائيًا بالاسم فقط.
- ثبّت `company_id` داخليًا واحتفظ بكل معرف خارجي كمرجع، لا كمفتاح وحيد.
- عند التعارض القوي أبقِ السجلين منفصلين للمراجعة.

**يغطي أيضًا:** الأسماء، العناوين، الملكية، والعقوبات لأن كل تلك Apps تحتاج الهوية الصحيحة.

