# 05 — الاستخراج المنظم

## الترتيب

نبحث أولًا عن JSON-LD وmicrodata وOpenGraph باستخدام [extruct](https://github.com/scrapinghub/extruct)، ثم JSON مضمّن أو API response، ثم CSS/XPath selectors. البيانات المنظمة أسرع، لكنها ادعاء من الصفحة وليست ضمانًا لحداثة القيمة.

كل extractor يعيد حقولًا موحدة مع: القيمة الأصلية، selector أو JSON path، confidence، أخطاء التحقق، رابط المصدر ووقت الرصد. نطبق schema validation وقواعد المجال بعد الاستخراج، لا داخله.

## مقاومة التغير

استخدم دلالات العنصر وlabels قبل classes المتغيرة، وضع أكثر من selector مرتب، واختبره على fixtures محفوظة. تغير layout يجب أن ينتج `parse_failure` لا قيمة صفرية أو سجلًا ناقصًا يبدو ناجحًا.

يمكن مشاركة محرك الاستخراج، لكن schemas تختلف: Tender وAward وProduct وOffer وCompany كيانات مستقلة.

