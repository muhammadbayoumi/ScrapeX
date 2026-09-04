# 19 — العقوبات وقوائم المراقبة

## الهدف

معرفة ما إذا كان الكيان نفسه ظاهرًا في قائمة عقوبات أو حظر رسمية، أو مملوكًا/مسيطرًا عليه بما يفعّل قاعدة قانونية. هذه نتيجة عالية الخطورة ولا تصلح بمطابقة اسم بسيطة.

## المصادر والأدوات

- القوائم الرسمية لكل جهة؛ مثال [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service).
- [OpenSanctions](https://www.opensanctions.org/docs/) يجمع قوائم وعلاقات ومعرفات متعددة.
- [yente](https://github.com/opensanctions/yente) API مفتوح للبحث والمطابقة الجماعية.
- [Nomenklatura](https://github.com/opensanctions/nomenklatura) لدمج كيانات FollowTheMoney.

## الترخيص

كود OpenSanctions/yente مفتوح، لكن **البيانات لها ترخيص منفصل**. النسخة bulk المجانية مخصصة للاستخدام غير التجاري تحت CC BY-NC 4.0 بحسب [صفحة الإعفاء التجاري](https://www.opensanctions.org/docs/commercial/exemption/). الاستخدام الشخصي المتوقع مناسب غالبًا، لكن راجع الشروط الحالية قبل التشغيل.

## المطابقة

استخدم الاسم والأسماء البديلة والبلد والعنوان ورقم التسجيل وLEI والتواريخ. النتيجة: `confirmed_match`, `possible_match`, `cleared`, `not_found`؛ و`cleared` يحتاج دليل فصل واضح لا مجرد درجة منخفضة.

## حدود

لا تستخدم النتيجة لاتخاذ قرار قانوني آلي. القوائم والقواعد مثل «50 Percent Rule» تتغير وتتطلب مختصًا وسياق اختصاص.

**يغطي أيضًا:** الملكية، المديرون، المخاطر، وحل الهوية.

