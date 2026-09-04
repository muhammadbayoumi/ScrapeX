# 06 — الصناعة والتصنيفات

## المطلوب

استخراج رموز الصناعة الرسمية ثم تحويلها إلى تصنيف موحّد يصلح للبحث والتجميع، مع فصل «ما سجلته الشركة» عن «ما استنتجه النظام من الموقع».

## المصادر

- رموز النشاط في السجل الوطني أو [OpenCorporates](https://api.opencorporates.com/documentation/API-Reference).
- [UN ISIC](https://unstats.un.org/unsd/classifications/econ) كتصنيف دولي مرجعي.
- NACE للاتحاد الأوروبي وNAICS لأمريكا الشمالية وSIC في أنظمة أخرى؛ استخدم جداول التحويل الرسمية عند وجودها.
- وصف النشاط في الإيداعات والموقع لتوليد تصنيف استدلالي.
- [Wikidata](https://www.wikidata.org/wiki/Help:Data_access) كإشارة مساعدة.

## نموذج النتيجة

```text
classification_system: ISIC_REV4
code: 6201
label: Computer programming activities
assignment: official | mapped | inferred
confidence: 0..1
```

## حدود

- الشركة قد تمارس أكثر من نشاط أو تسجل رمزًا واسعًا وقديمًا.
- الخرائط بين ISIC/NACE/NAICS ليست دائمًا واحدًا إلى واحد.
- لا تدّع أن تصنيفًا مستنتجًا رسمي؛ احتفظ بالطريقة والإصدار.

**يغطي أيضًا:** البحث القطاعي، المقارنة، اختيار مصادر تراخيص متخصصة، وتحليل العملاء المحتملين.

