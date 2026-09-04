# 12 — التخزين وإزالة التكرار والمصدر

## ثلاث طبقات

1. **Raw evidence:** response metadata وhash ولقطة مسموح بحفظها.
2. **Normalized records:** Tender/Product/Offer/Company schemas موحدة.
3. **Events:** إنشاء أو تعديل أو اختفاء مع before/after.

إزالة التكرار تبدأ بمعرف رسمي قوي؛ ثم مفاتيح مركبة كالمصدر+رقم الإعلان أو GTIN+variant+seller؛ ثم fuzzy matching كمرشح فقط. لا تدمج سجلين نهائيًا دون تفسير ودرجة ثقة وإمكانية فك الدمج.

لكل حقل نحفظ URL، `observed_at`، `published_at` إن وُجد، extractor/version، selector أو مسار JSON، confidence، والترخيص. نفصل «لم نجده» عن `null` المنشور وعن فشل الاستخراج.

يمكن استخدام [ArchiveBox](https://github.com/ArchiveBox/ArchiveBox) لحفظ أدلة الويب عندما تسمح الحقوق والسياسة. نحدد retention، ونحذف النسخ غير اللازمة والبيانات الشخصية، ولا نخزن كل شيء بلا غرض.
