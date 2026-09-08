# Marhalati 4.0 — Production-ready source package

## Android
This version is configured for a physical Android phone connected to the same Wi‑Fi as the Windows PC:
`http://192.168.0.126:8000`

If the PC IP changes, update `API_BASE_URL` in `app/build.gradle.kts` (BuildConfig)

## Backend on Windows
Open PowerShell in the `backend` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep this PowerShell window running while students use the app.

Test:
`http://192.168.0.126:8000/api/health`

Expected:
`{"ok":true,"service":"Marhalati","version":"3.0"}`

Default administrator:
University ID: `0110`
Password: `s`

The backend creates `marhalati.db` and `uploads` automatically.

## Included
- Modern dark student UI
- App icon
- Student registration/login
- Sections A/B/C/D
- Weekly courses
- Announcements
- In-app notifications
- Attendance records API
- Profile editing
- Password change
- Profile photo upload
- Lecture/file upload and download
- Admin course/announcement/file management
- Student listing for admin


## حقوق البرنامج
حقوق برنامج **مرحلتي (Marhalati4)** محفوظة للطالب **محمد صادق محمد عبدالحسن** © 2026.


## تحسينات الجودة في هذه النسخة
- تحسين SQLite باستخدام WAL وbusy timeout وفهارس للاستعلامات المتكررة.
- تنظيف جلسات الدخول المنتهية تلقائياً.
- إزالة مسار API مكرر في الملف الشخصي.
- التحقق من المرحلة عند إنشاء المادة، والتحقق من العناوين والنصوص المطلوبة.
- تقليل التحديث التلقائي من 30 إلى 60 ثانية لتخفيف استهلاك الشبكة وتحسين السلاسة.
- نقل عنوان الخادم إلى `BuildConfig.API_BASE_URL` لتسهيل نقل التطبيق من الكمبيوتر المحلي إلى خادم مستضاف.

## AppCreator24
AppCreator24 لا يستورد مشروع Android/Gradle هذا كملف APK مصدر. لدمج «مرحلتي» معه، استضف واجهة ويب للبرنامج على HTTPS ثم استخدم عنوانها داخل AppCreator24 كواجهة Web/WebView. أما الـ API الحالي فيمكن استضافته على خادم عام، ويجب أن يكون عنوان `API_BASE_URL` هو عنوان HTTPS الخاص به عند بناء نسخة الإنترنت.

## التحقق
تم فحص `backend/main.py` من ناحية Python syntax بعد التعديلات. إعادة بناء APK تحتاج Android Studio/Gradle مع إمكانية تنزيل dependencies؛ بيئة الفحص الحالية لا تملك اتصالاً خارجياً لتنزيل Gradle، لذلك لم أضع APK جديداً على أنه مُختبر دون بناء فعلي.
