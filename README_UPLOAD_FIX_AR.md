# إصلاح رفع الملفات

تم إصلاح رفع الملازم والمستندات من واجهة التدريسي.

يدعم النظام: PDF, DOC, DOCX, PPT, PPTX, TXT, JPG, JPEG, PNG حتى 20MB.

## تشغيل الخادم
```powershell
cd "C:\Users\bhadli\Downloads\Compressed\7\Marhalati4\backend"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```
