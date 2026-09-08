# تشغيل مشروع مرحلتي

## Android
1. افتح مجلد المشروع الرئيسي `marhalati` في Android Studio.
2. تأكد من أن `app/build.gradle.kts` يحتوي على عنوان الـ API الصحيح.
3. النسخة الحالية مضبوطة افتراضيًا على:
   `http://192.168.0.126:8001`
4. إذا تغيّر عنوان الكمبيوتر، غيّر قيمة `API_BASE_URL` فقط.
5. نفّذ **Sync Project with Gradle Files** ثم **Build > Rebuild Project** ثم شغّل التطبيق.

### هاتف حقيقي
يجب أن يكون الهاتف والكمبيوتر على نفس الشبكة، وأن يسمح جدار حماية Windows بالاتصال على TCP 8001.

### Android Emulator
للوصول إلى Backend يعمل على نفس الكمبيوتر استخدم:
`http://10.0.2.2:8001`

## Backend
من مجلد `backend`:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

أو في PowerShell:

```powershell
.\start_server.ps1
```

اختبار الخادم:
`http://127.0.0.1:8001/docs`

## ملاحظات
- لا تضف `local.properties` إلى ملفات المشروع المرسلة؛ فهو خاص بجهاز المطور.
- لا تغيّر قاعدة البيانات الحالية إذا كانت تحتوي على بيانات اختبار مهمة.
- عند نقل Backend إلى استضافة خارجية، غيّر `API_BASE_URL` إلى عنوان HTTPS الخاص بالخادم.
