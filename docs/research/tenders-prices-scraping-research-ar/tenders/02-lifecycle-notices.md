# 02 — دورة المناقصة والإشعارات

## المراحل

`planning → tender → award → contract → implementation`، وقد تنتهي العملية بالإلغاء أو عدم الترسية. الإعلان الواحد ليس المناقصة كلها؛ قد توجد notices للتخطيط والتعديل والنتيجة والعقد.

## الأساس المفتوح

[OCDS](https://standard.open-contracting.org/latest/en/) يصف releases متتابعة لنفس contracting process باستخدام `ocid`. أما [OC4IDS](https://standard.open-contracting.org/infrastructure/latest/en/reference/) فيضيف دورة مشروع البنية التحتية ويربطها بعمليات التعاقد.

## النموذج المقترح

- `procedure`: العملية الموحدة.
- `notice`: كل إعلان/نسخة كما نشرها المصدر.
- `lot`: جزء يمكن التقديم عليه منفصلًا.
- `award` و`contract` و`implementation_update`.
- `event`: نشر، تعديل، تمديد، إلغاء، ترسية أو إنهاء.

## قواعد

- احتفظ بالنص والحالة الأصلية ثم map إلى حالة معيارية.
- افصل تاريخ النشر عن بداية/نهاية التقديم وعن تاريخ الحدث.
- لا تعتبر award عقدًا منفذًا أو مبلغ contract إنفاقًا فعليًا.
- إذا لم ينشر المصدر إلا مرحلة tender، اعرض بقية المراحل `not_published` لا `not_exists`.

**تغطي هذه النقطة:** التغييرات، المواعيد، الترسية، وتحليل مدة العملية.

