# 06 — المواعيد والقيمة والأجزاء والأهلية

## الحقول

موعد الأسئلة، briefing/site visit، نهاية التقديم، timezone، قيمة تقديرية وحدودها، العملة، مدة العقد، الضمان، التسجيلات المطلوبة، الدولة/مكان التنفيذ، وlots.

## المعالجة

- حوّل التوقيت إلى UTC مع الاحتفاظ بالنص والمنطقة الأصلية.
- افصل `estimated_value`, `award_value`, `contract_value`, و`paid_amount`.
- اجعل كل lot فرصة فرعية؛ قد تختلف القيمة والموعد والأهلية.
- استخرج الشروط كقائمة evidence، لا كحكم آلي «مؤهل» إلا للقواعد الواضحة.

## مصادر منظمة

[OCDS](https://standard.open-contracting.org/latest/en/) يوفر periods/value/items/lots عبر النموذج والامتدادات، و[TED](https://docs.ted.europa.eu/api/latest/search.html) يوفر CPV/NUTS وحقول notices الأوروبية.

## التنبيه

أنشئ `deadline_at`, `timezone`, `days_remaining`, و`deadline_confidence`. إذا عدّل المصدر الموعد، لا تحذف السابق؛ سجله كحدث وبلّغ المستخدم.

## حدود

قد تكون القيمة range أو سرية أو تشمل عدة سنوات/ضرائب. «موعد التقديم» الظاهر في صفحة نتائج قد يكون قديمًا بعد corrigendum؛ المستند/الإشعار الأحدث يتقدم.

