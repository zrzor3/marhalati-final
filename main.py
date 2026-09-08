import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DB = BASE_DIR / "marhalati.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Marhalati API", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
SESSION_DAYS = 30

COLLEGES = {
    "كلية الهندسة": [
        "هندسة تقنيات الحاسوب",
        "هندسة تقنيات الاتصالات",
        "هندسة تقنيات الأجهزة الطبية"
    ],
    "كلية الصيدلة": [
        "الصيدلة"
    ],
    "كلية التربية": [
        "تربية اللغة العربية",
        "تربية اللغة الإنجليزية",
        "تربية علوم القرآن",
        "التأهيل السلوكي للتوحد"
    ],
    "كلية العلوم الإدارية والمالية": [
        "إدارة الأعمال",
        "المحاسبة",
        "اقتصاديات النفط والغاز"
    ],
    "كلية القانون والسياسة": [
        "القانون",
        "العلوم السياسية"
    ],
    "كلية الآداب": [
        "التاريخ",
        "الإعلام",
        "علم النفس السريري"
    ],
}
SECTIONS = {"A", "B", "C", "D"}
STAGES = {"المرحلة الأولى", "المرحلة الثانية", "المرحلة الثالثة", "المرحلة الرابعة"}


def db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120000).hex()
        return hmac.compare_digest(actual, digest_hex)
    except Exception:
        return False


def add_column(c, table, column, definition):
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        university_id TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        college TEXT NOT NULL DEFAULT '',
        department TEXT NOT NULL DEFAULT '',
        section TEXT NOT NULL DEFAULT 'A',
        stage TEXT NOT NULL DEFAULT 'المرحلة الأولى',
        is_active INTEGER NOT NULL DEFAULT 1,
        role TEXT NOT NULL DEFAULT 'student',
        photo_path TEXT DEFAULT '',
        lecturer_course_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS courses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT NOT NULL,
        lecturer TEXT NOT NULL,
        room TEXT NOT NULL,
        day TEXT NOT NULL,
        time TEXT NOT NULL,
        college TEXT NOT NULL DEFAULT '',
        department TEXT NOT NULL DEFAULT '',
        section TEXT NOT NULL DEFAULT 'A',
        stage TEXT NOT NULL DEFAULT 'المرحلة الأولى'
    );
    CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,body TEXT NOT NULL,college TEXT NOT NULL DEFAULT '',department TEXT NOT NULL DEFAULT '',stage TEXT NOT NULL DEFAULT '',section TEXT NOT NULL DEFAULT 'ALL',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires_at TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT NOT NULL,body TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,course_id INTEGER NOT NULL,status TEXT NOT NULL,note TEXT DEFAULT '',date TEXT DEFAULT CURRENT_DATE,UNIQUE(user_id,course_id,date));
    CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,file_name TEXT NOT NULL,stored_name TEXT NOT NULL,course_id INTEGER,college TEXT NOT NULL DEFAULT '',department TEXT NOT NULL DEFAULT '',stage TEXT NOT NULL DEFAULT '',section TEXT NOT NULL DEFAULT 'ALL',uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS audit_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        actor_user_id INTEGER,
        actor_name TEXT NOT NULL DEFAULT '',
        actor_role TEXT NOT NULL DEFAULT '',
        target_user_id INTEGER,
        target_name TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    c.executescript("""
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
    CREATE INDEX IF NOT EXISTS idx_users_scope ON users(role,college,department,stage,section);
    CREATE INDEX IF NOT EXISTS idx_courses_scope ON courses(college,department,stage,section);
    CREATE INDEX IF NOT EXISTS idx_files_scope ON files(college,department,stage,section);
    CREATE INDEX IF NOT EXISTS idx_announcements_scope ON announcements(college,department,stage,section);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,is_read,created_at);
    CREATE INDEX IF NOT EXISTS idx_attendance_user_date ON attendance(user_id,date);
    CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
    """)
    add_column(c, "users", "college", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "users", "department", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "users", "stage", "TEXT NOT NULL DEFAULT 'المرحلة الأولى'")
    add_column(c, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
    add_column(c, "users", "photo_path", "TEXT DEFAULT ''")
    add_column(c, "users", "lecturer_course_id", "INTEGER")
    add_column(c, "courses", "college", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "courses", "department", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "courses", "stage", "TEXT NOT NULL DEFAULT 'المرحلة الأولى'")
    add_column(c, "files", "college", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "files", "department", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "files", "stage", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "announcements", "college", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "announcements", "department", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "announcements", "stage", "TEXT NOT NULL DEFAULT ''")
    add_column(c, "announcements", "section", "TEXT NOT NULL DEFAULT 'ALL'")
    admin = c.execute("SELECT 1 FROM users WHERE university_id='0110'").fetchone()
    if not admin:
        c.execute("INSERT INTO users(name,university_id,password_hash,college,department,section,stage,is_active,role,photo_path) VALUES(?,?,?,?,?,?,?,?,?,?)", ("مسؤول مرحلتي", "0110", hash_password("s"), "", "", "ALL", "المرحلة الأولى", 1, "admin", ""))
    c.execute("DELETE FROM sessions WHERE expires_at<=?", (datetime.now(timezone.utc).isoformat(),))
    c.commit()
    c.close()


def validate_academic(college, department, section, stage=None):
    if college not in COLLEGES:
        raise HTTPException(400, "الكلية غير صحيحة")
    if department not in COLLEGES[college]:
        raise HTTPException(400, "القسم لا يتبع الكلية المختارة")
    if section not in SECTIONS:
        raise HTTPException(400, "الشعبة غير صحيحة")
    if stage is not None and stage not in STAGES:
        raise HTTPException(400, "المرحلة غير صحيحة")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def auth(authorization: Optional[str], admin=False):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "غير مصرح")
    raw = authorization[7:].strip()
    c = db()
    row = c.execute("""
        SELECT u.* FROM sessions s
        JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?
    """, (token_hash(raw), datetime.now(timezone.utc).isoformat())).fetchone()
    c.close()
    if not row:
        raise HTTPException(401, "انتهت الجلسة، يرجى تسجيل الدخول")
    if row["role"] != "admin" and not row["is_active"]:
        raise HTTPException(403, "الحساب معطل من قبل المسؤول")
    if admin and not (row["role"] == "admin" and row["university_id"] == "0110"):
        raise HTTPException(403, "صلاحية المسؤول الأعلى مطلوبة")
    return row


def notify_users(title, body, college=None, department=None, stage=None, section=None):
    c = db()
    query = "SELECT id FROM users WHERE role='student'"
    args = []
    if college:
        query += " AND college=?"; args.append(college)
    if department:
        query += " AND department=?"; args.append(department)
    if stage:
        query += " AND stage=?"; args.append(stage)
    if section and section != "ALL":
        query += " AND section=?"; args.append(section)
    ids = c.execute(query, args).fetchall()
    c.executemany(
        "INSERT INTO notifications(user_id,title,body) VALUES(?,?,?)",
        [(r["id"], title, body) for r in ids]
    )
    c.commit(); c.close()


def log_event(event_type, actor=None, target=None, details=""):
    c = db()
    c.execute(
        """INSERT INTO audit_logs(event_type,actor_user_id,actor_name,actor_role,target_user_id,target_name,details)
           VALUES(?,?,?,?,?,?,?)""",
        (
            event_type,
            actor["id"] if actor is not None else None,
            actor["name"] if actor is not None else "",
            actor["role"] if actor is not None else "",
            target["id"] if target is not None else None,
            target["name"] if target is not None else "",
            details,
        )
    )
    c.commit(); c.close()


def lecturer_course(user):
    if user["role"] != "lecturer" or not user["lecturer_course_id"]:
        raise HTTPException(403, "صلاحية التدريسي مطلوبة")
    c = db(); row = c.execute("SELECT * FROM courses WHERE id=?", (user["lecturer_course_id"],)).fetchone(); c.close()
    if not row:
        raise HTTPException(403, "المادة المرتبطة بحساب التدريسي غير موجودة")
    return row


init_db()


class Register(BaseModel):
    name: str
    password: str
    college: str
    department: str
    section: str
    stage: str

class LecturerRegister(BaseModel):
    name: str
    employee_id: str
    password: str
    course_name: str
    course_code: str
    college: str
    department: str
    section: str
    stage: str

class Login(BaseModel):
    university_id: str
    password: str

class ProfileUpdate(BaseModel):
    name: str
    section: str

class AdminStudentUpdate(BaseModel):
    name: str
    college: str
    department: str
    stage: str
    section: str

class AdminPasswordReset(BaseModel):
    new_password: str

class AdminLecturerUpdate(BaseModel):
    name: str
    course_name: str
    course_code: str
    college: str
    department: str
    section: str
    stage: str

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

class Course(BaseModel):
    name: str
    code: str
    lecturer: str
    room: str
    day: str
    time: str
    college: str
    department: str
    section: str
    stage: str = "المرحلة الأولى"

class Announcement(BaseModel):
    title: str
    body: str
    college: str
    department: str
    stage: str
    section: str = "ALL"

class AttendanceUpdate(BaseModel):
    user_id: int
    course_id: int
    status: str
    note: str = ""


@app.get("/api/health")
def health():
    return {"ok": True, "service": "Marhalati", "version": "4.0", "colleges": len(COLLEGES)}


def user_payload(u, token):
    return {"token": token, "name": u["name"], "university_id": u["university_id"], "college": u["college"], "department": u["department"], "section": u["section"], "stage": u["stage"], "role": u["role"], "super_admin": bool(u["role"] == "admin" and u["university_id"] == "0110"), "lecturer_course_id": u["lecturer_course_id"] or 0, "photo_url": f"/api/profile/photo/{u['id']}" if u["photo_path"] else ""}


def next_student_university_id(c):
    """Generate the next positive numeric student university ID.
    The ID is assigned by the server, not entered by the student.
    0110 is reserved for the super-admin account.
    """
    rows = c.execute("SELECT university_id FROM users").fetchall()
    used = set()
    for row in rows:
        value = str(row["university_id"] or "").strip()
        if value.isdigit():
            used.add(int(value))
    candidate = 1
    while candidate in used or str(candidate).zfill(4) == "0110":
        candidate += 1
    return str(candidate)


@app.post("/api/register")
def register(x: Register):
    name = " ".join(x.name.strip().split())
    if len(name.split()) < 3 or len(x.password) < 4:
        raise HTTPException(400, "أدخل الاسم الثلاثي ورمز حساب لا يقل عن 4 أحرف")
    validate_academic(x.college, x.department, "A" if x.section == "ALL" else x.section, x.stage)
    c = db()
    try:
        # Lock the SQLite write transaction so two students cannot receive the same serial.
        c.execute("BEGIN IMMEDIATE")
        university_id = next_student_university_id(c)
        c.execute(
            "INSERT INTO users(name,university_id,password_hash,college,department,section,stage,is_active,role,photo_path) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name, university_id, hash_password(x.password), x.college, x.department, x.section, x.stage, 1, "student", "")
        )
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback(); c.close(); raise HTTPException(409, "تعذر إنشاء الرقم الجامعي، حاول مرة أخرى")
    except Exception:
        c.rollback(); c.close(); raise
    created = c.execute("SELECT * FROM users WHERE university_id=?", (university_id,)).fetchone()
    c.close()
    log_event("REGISTER", created, created, f"تسجيل حساب طالب جديد - الرقم الجامعي المولد تلقائياً: {university_id}")
    result = login(Login(university_id=university_id, password=x.password))
    result["assigned_university_id"] = university_id
    result["message"] = f"تم التسجيل بنجاح. الرقم الجامعي الخاص بك هو {university_id}"
    return result


@app.post("/api/lecturer/register")
def lecturer_register(x: LecturerRegister):
    if len(x.name.strip()) < 2 or len(x.employee_id.strip()) < 2 or len(x.password) < 4:
        raise HTTPException(400, "أدخل بيانات التدريسي بشكل صحيح")
    if len(x.course_name.strip()) < 2 or len(x.course_code.strip()) < 1:
        raise HTTPException(400, "أدخل اسم المادة ورمزها")
    validate_academic(x.college, x.department, x.section, x.stage)
    c = db()
    try:
        existing_course = c.execute(
            "SELECT * FROM courses WHERE code=? AND college=? AND department=? AND section=? AND stage=?",
            (x.course_code.strip(), x.college, x.department, x.section, x.stage)
        ).fetchone()
        if existing_course:
            course_id = existing_course["id"]
            c.execute("UPDATE courses SET name=?, lecturer=? WHERE id=?", (x.course_name.strip(), x.name.strip(), course_id))
        else:
            cur = c.execute(
                "INSERT INTO courses(name,code,lecturer,room,day,time,college,department,section,stage) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (x.course_name.strip(), x.course_code.strip(), x.name.strip(), "", "", "", x.college, x.department, x.section, x.stage)
            )
            course_id = cur.lastrowid
        cur = c.execute(
            "INSERT INTO users(name,university_id,password_hash,college,department,section,stage,is_active,role,photo_path,lecturer_course_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (x.name.strip(), x.employee_id.strip(), hash_password(x.password), x.college, x.department, x.section, x.stage, 1, "lecturer", "", course_id)
        )
        user_id = cur.lastrowid
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback(); c.close(); raise HTTPException(409, "رقم التدريسي مستخدم مسبقاً")
    created = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone(); c.close()
    log_event("LECTURER_REGISTER", created, created, f"تسجيل حساب تدريسي للمادة {x.course_name.strip()} ({x.course_code.strip()})")
    return login(Login(university_id=x.employee_id, password=x.password))


@app.post("/api/login")
def login(x: Login):
    c = db(); u = c.execute("SELECT * FROM users WHERE university_id=?", (x.university_id.strip(),)).fetchone(); c.close()
    if not u or not verify_password(x.password, u["password_hash"]): raise HTTPException(401, "الرقم الجامعي أو الرمز غير صحيح")
    if u["role"] != "admin" and not u["is_active"]: raise HTTPException(403, "الحساب معطل من قبل المسؤول")
    token = secrets.token_urlsafe(32)
    c = db()
    # Keep the sessions table small so login/auth stay fast over time.
    c.execute("DELETE FROM sessions WHERE expires_at<=?", (datetime.now(timezone.utc).isoformat(),))
    c.execute(
        "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
        (token_hash(token), u["id"], (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat())
    )
    c.commit(); c.close()
    log_event("LOGIN", u, u, "تسجيل دخول")
    return user_payload(u, token)


@app.get("/api/me")
def me(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db(); row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone(); c.close()
    return {"name": row["name"], "university_id": row["university_id"], "college": row["college"], "department": row["department"], "section": row["section"], "stage": row["stage"], "role": row["role"], "super_admin": bool(row["role"] == "admin" and row["university_id"] == "0110"), "lecturer_course_id": row["lecturer_course_id"] or 0, "photo_url": f"/api/profile/photo/{row['id']}" if row["photo_path"] else ""}


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return {"ok": True}
    raw_hash = token_hash(authorization[7:].strip())
    c = db(); u = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (raw_hash,)).fetchone(); c.execute("DELETE FROM sessions WHERE token_hash=?", (raw_hash,)); c.commit(); c.close()
    if u: log_event("LOGOUT", u, u, "خروج المستخدم من الحساب")
    return {"ok": True}


@app.put("/api/profile")
def update_profile(x: ProfileUpdate, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); validate_section = x.section in SECTIONS
    if not x.name.strip() or not validate_section: raise HTTPException(400, "بيانات الملف الشخصي غير صحيحة")
    c = db(); c.execute("UPDATE users SET name=?,section=? WHERE id=?", (x.name.strip(), x.section, u["id"])); c.commit(); c.close()
    return {"ok": True}


@app.put("/api/profile/password")
def update_password(x: PasswordUpdate, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization)
    if len(x.new_password) < 4: raise HTTPException(400, "الرمز الجديد قصير جداً")
    c = db(); row = c.execute("SELECT password_hash FROM users WHERE id=?", (u["id"],)).fetchone()
    if not row or not verify_password(x.current_password, row["password_hash"]): c.close(); raise HTTPException(400, "الرمز الحالي غير صحيح")
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(x.new_password), u["id"])); c.commit(); c.close(); return {"ok": True}


@app.post("/api/profile/photo")
async def upload_photo(photo: UploadFile = File(...), authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); suffix = Path(photo.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}: raise HTTPException(400, "الصورة يجب أن تكون JPG أو PNG أو WEBP")
    data = await photo.read()
    if len(data) > 5 * 1024 * 1024: raise HTTPException(400, "حجم الصورة أكبر من 5MB")
    stored = f"profile_{u['id']}_{uuid.uuid4().hex}{suffix}"; (UPLOAD_DIR / stored).write_bytes(data)
    c = db(); old = c.execute("SELECT photo_path FROM users WHERE id=?", (u["id"],)).fetchone()
    if old and old["photo_path"]:
        p = UPLOAD_DIR / old["photo_path"]
        if p.exists(): p.unlink(missing_ok=True)
    c.execute("UPDATE users SET photo_path=? WHERE id=?", (stored, u["id"])); c.commit(); c.close()
    return {"ok": True, "photo_url": f"/api/profile/photo/{u['id']}"}


@app.get("/api/profile/photo/{user_id}")
def get_photo(user_id: int):
    c = db(); row = c.execute("SELECT photo_path FROM users WHERE id=?", (user_id,)).fetchone(); c.close()
    if not row or not row["photo_path"]: raise HTTPException(404, "لا توجد صورة")
    path = UPLOAD_DIR / row["photo_path"]
    if not path.exists(): raise HTTPException(404, "الصورة غير موجودة")
    return FileResponse(path)


@app.get("/api/courses")
def courses(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db()
    if u["role"] == "admin": rows = c.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
    elif u["role"] == "lecturer": rows = c.execute("SELECT * FROM courses WHERE id=?", (u["lecturer_course_id"],)).fetchall()
    else:
        rows = c.execute("SELECT * FROM courses WHERE college=? AND department=? AND stage=? AND (section=? OR section='ALL') ORDER BY id DESC", (u["college"], u["department"], u["stage"], u["section"])).fetchall()
    c.close(); return [dict(r) for r in rows]


@app.post("/api/admin/courses")
def add_course(x: Course, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True)
    validate_academic(x.college, x.department, x.section, x.stage)
    if not x.name.strip() or not x.code.strip() or not x.lecturer.strip():
        raise HTTPException(400, "اسم المادة والرمز واسم التدريسي مطلوبة")
    c = db()
    cur = c.execute("INSERT INTO courses(name,code,lecturer,room,day,time,college,department,section,stage) VALUES(?,?,?,?,?,?,?,?,?,?)", (x.name.strip(), x.code.strip(), x.lecturer.strip(), x.room.strip(), x.day.strip(), x.time.strip(), x.college, x.department, x.section, x.stage))
    c.commit(); course_id = cur.lastrowid; c.close()
    notify_users("محاضرة جديدة", f"تمت إضافة {x.name} • {x.day} • {x.time}", x.college, x.department, None, x.section); return {"id": course_id}


@app.delete("/api/admin/courses/{cid}")
def del_course(cid: int, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); c = db(); c.execute("DELETE FROM courses WHERE id=?", (cid,)); c.execute("DELETE FROM attendance WHERE course_id=?", (cid,)); c.commit(); c.close(); return {"ok": True}


@app.get("/api/announcements")
def announcements(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db()
    if u["role"] == "admin":
        rows = c.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
    else:
        rows = c.execute("""
            SELECT * FROM announcements
            WHERE (college='' OR college=?)
              AND (department='' OR department=?)
              AND (stage='' OR stage=?)
              AND (section='ALL' OR section=?)
            ORDER BY id DESC
        """, (u["college"], u["department"], u["stage"], u["section"])).fetchall()
    c.close(); return [dict(r) for r in rows]


@app.post("/api/admin/announcements")
def add_announcement(x: Announcement, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True)
    validate_academic(x.college, x.department, "A" if x.section == "ALL" else x.section, x.stage)
    if not x.title.strip() or not x.body.strip():
        raise HTTPException(400, "عنوان الإعلان ونصه مطلوبان")
    c = db()
    cur = c.execute(
        "INSERT INTO announcements(title,body,college,department,stage,section) VALUES(?,?,?,?,?,?)",
        (x.title.strip(), x.body.strip(), x.college, x.department, x.stage, x.section)
    )
    c.commit(); aid = cur.lastrowid; c.close()
    notify_users(x.title, x.body, x.college, x.department, x.stage, x.section)
    return {"id": aid}


@app.delete("/api/admin/announcements/{aid}")
def del_announcement(aid: int, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); c = db(); c.execute("DELETE FROM announcements WHERE id=?", (aid,)); c.commit(); c.close(); return {"ok": True}


@app.get("/api/notifications")
def notifications(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db(); rows = c.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", (u["id"],)).fetchall(); c.close(); return [dict(r) for r in rows]


@app.post("/api/notifications/{nid}/read")
def read_notification(nid: int, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db(); c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, u["id"])); c.commit(); c.close(); return {"ok": True}


@app.get("/api/attendance")
def my_attendance(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db(); rows = c.execute("SELECT a.*, c.name AS course_name, c.code FROM attendance a JOIN courses c ON c.id=a.course_id WHERE a.user_id=? ORDER BY a.date DESC,a.id DESC", (u["id"],)).fetchall(); c.close(); return [dict(r) for r in rows]


@app.get("/api/admin/students")
def students(authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); c = db(); rows = c.execute("SELECT id,name,university_id,college,department,section,stage,is_active,role,photo_path FROM users WHERE role='student' ORDER BY id DESC").fetchall(); c.close()
    return [{**dict(r), "photo_url": f"/api/profile/photo/{r['id']}" if r["photo_path"] else ""} for r in rows]


@app.put("/api/admin/students/{student_id}")
def update_student(student_id: int, x: AdminStudentUpdate, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    validate_academic(x.college, x.department, x.section, x.stage)
    if len(x.name.strip()) < 2:
        raise HTTPException(400, "اسم الطالب غير صحيح")
    c = db(); row = c.execute("SELECT role FROM users WHERE id=?", (student_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "الطالب غير موجود")
    if row["role"] != "student": c.close(); raise HTTPException(400, "لا يمكن تعديل حساب مسؤول من هذه الواجهة")
    c.execute("UPDATE users SET name=?,college=?,department=?,stage=?,section=? WHERE id=?", (x.name.strip(), x.college, x.department, x.stage, x.section, student_id))
    c.commit(); target = c.execute("SELECT * FROM users WHERE id=?", (student_id,)).fetchone(); c.close(); log_event("PROFILE_UPDATE", actor, target, "تعديل بيانات الطالب"); return {"ok": True}

@app.patch("/api/admin/students/{student_id}/status")
def toggle_student(student_id: int, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    c = db(); row = c.execute("SELECT role,is_active FROM users WHERE id=?", (student_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "الطالب غير موجود")
    if row["role"] != "student": c.close(); raise HTTPException(400, "لا يمكن تغيير حالة حساب مسؤول")
    new_status = 0 if row["is_active"] else 1
    c.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, student_id)); c.commit(); c.close()
    c2 = db(); target = c2.execute("SELECT * FROM users WHERE id=?", (student_id,)).fetchone()
    if not new_status: c2.execute("DELETE FROM sessions WHERE user_id=?", (student_id,))
    c2.commit(); c2.close()
    log_event("ACCOUNT_ENABLED" if new_status else "ACCOUNT_DISABLED", actor, target, "تغيير حالة الحساب")
    return {"ok": True, "is_active": bool(new_status)}

@app.post("/api/admin/students/{student_id}/password")
def reset_student_password(student_id: int, x: AdminPasswordReset, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    if len(x.new_password) < 4: raise HTTPException(400, "الرمز الجديد يجب أن يكون 4 أحرف على الأقل")
    c = db(); row = c.execute("SELECT role FROM users WHERE id=?", (student_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "الطالب غير موجود")
    if row["role"] != "student": c.close(); raise HTTPException(400, "لا يمكن تغيير رمز حساب مسؤول")
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(x.new_password), student_id)); c.commit(); c.close()
    c2 = db(); target = c2.execute("SELECT * FROM users WHERE id=?", (student_id,)).fetchone(); c2.execute("DELETE FROM sessions WHERE user_id=?", (student_id,)); c2.commit(); c2.close()
    log_event("PASSWORD_RESET", actor, target, "إعادة تعيين الرمز وطرد الجلسات")
    return {"ok": True}

@app.post("/api/admin/students/{student_id}/kick")
def kick_student(student_id: int, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    c = db(); target = c.execute("SELECT * FROM users WHERE id=?", (student_id,)).fetchone()
    if not target: c.close(); raise HTTPException(404, "المستخدم غير موجود")
    if target["role"] == "admin": c.close(); raise HTTPException(400, "لا يمكن طرد المسؤول العام")
    c.execute("DELETE FROM sessions WHERE user_id=?", (student_id,)); c.commit(); c.close()
    log_event("KICK", actor, target, "طرد المستخدم من جميع الجلسات")
    return {"ok": True}

@app.delete("/api/admin/students/{student_id}")
def delete_student(student_id: int, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    c = db(); row = c.execute("SELECT * FROM users WHERE id=?", (student_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "الطالب غير موجود")
    if row["role"] != "student": c.close(); raise HTTPException(400, "لا يمكن حذف حساب مسؤول")
    c.execute("DELETE FROM notifications WHERE user_id=?", (student_id,))
    c.execute("DELETE FROM attendance WHERE user_id=?", (student_id,))
    c.execute("DELETE FROM users WHERE id=?", (student_id,)); c.commit(); c.close()
    if row["photo_path"]:
        p = UPLOAD_DIR / row["photo_path"]
        if p.exists(): p.unlink(missing_ok=True)
    c2 = db(); c2.execute("DELETE FROM sessions WHERE user_id=?", (student_id,)); c2.commit(); c2.close()
    log_event("DELETE_ACCOUNT", actor, row, "حذف حساب طالب")
    return {"ok": True}

@app.get("/api/admin/lecturers")
def lecturers(authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); c = db()
    rows = c.execute("""SELECT u.id,u.name,u.university_id,u.college,u.department,u.section,u.stage,u.is_active,u.role,u.lecturer_course_id,
        c.name AS course_name,c.code AS course_code FROM users u LEFT JOIN courses c ON c.id=u.lecturer_course_id WHERE u.role='lecturer' ORDER BY u.id DESC""").fetchall(); c.close()
    return [dict(r) for r in rows]

@app.patch("/api/admin/lecturers/{lecturer_id}/status")
def toggle_lecturer(lecturer_id: int, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    c = db(); row = c.execute("SELECT * FROM users WHERE id=? AND role='lecturer'", (lecturer_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "التدريسي غير موجود")
    new_status = 0 if row["is_active"] else 1
    c.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, lecturer_id))
    if not new_status: c.execute("DELETE FROM sessions WHERE user_id=?", (lecturer_id,))
    c.commit(); target = c.execute("SELECT * FROM users WHERE id=?", (lecturer_id,)).fetchone(); c.close()
    log_event("LECTURER_ENABLED" if new_status else "LECTURER_DISABLED", actor, target, "تغيير حالة حساب التدريسي")
    return {"ok": True, "is_active": bool(new_status)}

@app.post("/api/admin/lecturers/{lecturer_id}/password")
def reset_lecturer_password(lecturer_id: int, x: AdminPasswordReset, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    if len(x.new_password) < 4: raise HTTPException(400, "الرمز الجديد يجب أن يكون 4 أحرف على الأقل")
    c = db(); row = c.execute("SELECT * FROM users WHERE id=? AND role='lecturer'", (lecturer_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "التدريسي غير موجود")
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(x.new_password), lecturer_id)); c.execute("DELETE FROM sessions WHERE user_id=?", (lecturer_id,)); c.commit(); target = c.execute("SELECT * FROM users WHERE id=?", (lecturer_id,)).fetchone(); c.close()
    log_event("LECTURER_PASSWORD_RESET", actor, target, "إعادة تعيين رمز التدريسي وطرد جلساته")
    return {"ok": True}

@app.put("/api/admin/lecturers/{lecturer_id}")
def update_lecturer(lecturer_id: int, x: AdminLecturerUpdate, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    validate_academic(x.college, x.department, x.section, x.stage)
    if len(x.name.strip()) < 2 or not x.course_name.strip() or not x.course_code.strip(): raise HTTPException(400, "بيانات التدريسي أو المادة غير صحيحة")
    c = db(); lecturer = c.execute("SELECT * FROM users WHERE id=? AND role='lecturer'", (lecturer_id,)).fetchone()
    if not lecturer: c.close(); raise HTTPException(404, "التدريسي غير موجود")
    course_id = lecturer["lecturer_course_id"]
    if course_id:
        c.execute("UPDATE courses SET name=?,code=?,lecturer=?,college=?,department=?,section=?,stage=? WHERE id=?", (x.course_name.strip(), x.course_code.strip(), x.name.strip(), x.college, x.department, x.section, x.stage, course_id))
    else:
        cur=c.execute("INSERT INTO courses(name,code,lecturer,room,day,time,college,department,section,stage) VALUES(?,?,?,?,?,?,?,?,?,?)", (x.course_name.strip(),x.course_code.strip(),x.name.strip(),"","","",x.college,x.department,x.section,x.stage)); course_id=cur.lastrowid
    c.execute("UPDATE users SET name=?,college=?,department=?,section=?,stage=?,lecturer_course_id=? WHERE id=?", (x.name.strip(),x.college,x.department,x.section,x.stage,course_id,lecturer_id)); c.commit(); target=c.execute("SELECT * FROM users WHERE id=?", (lecturer_id,)).fetchone(); c.close()
    log_event("LECTURER_UPDATE", actor, target, f"تعديل بيانات التدريسي والمادة: {x.course_name.strip()}")
    return {"ok": True}

@app.delete("/api/admin/lecturers/{lecturer_id}")
def delete_lecturer(lecturer_id: int, authorization: Optional[str] = Header(default=None)):
    actor = auth(authorization, True)
    c=db(); row=c.execute("SELECT * FROM users WHERE id=? AND role='lecturer'", (lecturer_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404, "التدريسي غير موجود")
    course_id=row["lecturer_course_id"]
    c.execute("DELETE FROM sessions WHERE user_id=?", (lecturer_id,)); c.execute("DELETE FROM users WHERE id=?", (lecturer_id,))
    if course_id: c.execute("DELETE FROM attendance WHERE course_id=?", (course_id,)); c.execute("DELETE FROM courses WHERE id=?", (course_id,))
    c.commit(); c.close(); log_event("LECTURER_DELETE", actor, row, "حذف حساب التدريسي ومادته المرتبطة")
    return {"ok": True}

@app.post("/api/admin/kick-all")
def kick_all_users(authorization: Optional[str] = Header(default=None)):
    actor=auth(authorization, True); c=db(); rows=c.execute("SELECT * FROM users WHERE university_id!='0110'").fetchall(); c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE university_id!='0110')"); c.commit(); c.close()
    for target in rows: log_event("KICK_ALL", actor, target, "طرد المستخدم من جميع الجلسات بواسطة المسؤول الأعلى")
    return {"ok": True, "count": len(rows)}

@app.get("/api/admin/audit-logs")
def audit_logs(limit: int = 250, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); limit = max(1, min(limit, 1000)); c = db()
    rows = c.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall(); c.close()
    return [dict(r) for r in rows]

@app.get("/api/lecturer/students")
def lecturer_students(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u); c = db()
    rows = c.execute("""SELECT id,name,university_id,college,department,section,stage,is_active FROM users
        WHERE role='student' AND is_active=1 AND college=? AND department=? AND stage=? AND section=? ORDER BY name""",
        (course["college"], course["department"], course["stage"], course["section"])).fetchall(); c.close()
    return [dict(r) for r in rows]

@app.post("/api/lecturer/attendance")
def lecturer_set_attendance(x: AttendanceUpdate, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u)
    if x.course_id != course["id"]: raise HTTPException(403, "لا يمكنك إدارة حضور مادة أخرى")
    if x.status not in {"حاضر", "غائب", "متأخر"}: raise HTTPException(400, "حالة الحضور غير صحيحة")
    c = db(); student = c.execute("SELECT * FROM users WHERE id=? AND role='student'", (x.user_id,)).fetchone()
    if not student or student["college"] != course["college"] or student["department"] != course["department"] or student["stage"] != course["stage"] or student["section"] != course["section"]:
        c.close(); raise HTTPException(403, "الطالب لا يتبع هذه المادة")
    c.execute("INSERT INTO attendance(user_id,course_id,status,note,date) VALUES(?,?,?,?,CURRENT_DATE) ON CONFLICT(user_id,course_id,date) DO UPDATE SET status=excluded.status,note=excluded.note", (x.user_id, x.course_id, x.status, x.note)); c.commit(); c.close()
    log_event("ATTENDANCE_UPDATE", u, student, f"{course['name']}: {x.status}")
    return {"ok": True}

@app.post("/api/lecturer/students/{student_id}/kick")
def lecturer_kick_student(student_id: int, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u); c = db()
    target = c.execute("SELECT * FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
    if not target:
        c.close(); raise HTTPException(404, "الطالب غير موجود")
    if not (target["college"] == course["college"] and target["department"] == course["department"] and target["stage"] == course["stage"] and target["section"] == course["section"]):
        c.close(); raise HTTPException(403, "لا يمكنك طرد طالب خارج مادتك")
    c.execute("DELETE FROM sessions WHERE user_id=?", (student_id,)); c.commit(); c.close()
    log_event("LECTURER_KICK", u, target, f"طرد الطالب من جلساته بواسطة تدريسي مادة {course['name']}")
    return {"ok": True}

class LecturerScheduleUpdate(BaseModel):
    room: str
    day: str
    time: str

@app.put("/api/lecturer/schedule")
def lecturer_update_schedule(x: LecturerScheduleUpdate, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u)
    if not x.day.strip() or not x.time.strip(): raise HTTPException(400, "اليوم والوقت مطلوبان")
    c = db(); c.execute("UPDATE courses SET room=?,day=?,time=? WHERE id=?", (x.room.strip(), x.day.strip(), x.time.strip(), course["id"])); c.commit(); updated = c.execute("SELECT * FROM courses WHERE id=?", (course["id"],)).fetchone(); c.close()
    log_event("LECTURER_SCHEDULE_UPDATE", u, None, f"تحديث جدول مادة {course['name']}: {x.day} {x.time} - {x.room}")
    return dict(updated)

@app.post("/api/lecturer/files")
async def lecturer_upload_file(title: str = Form(...), file: UploadFile = File(...), authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u)
    if not title.strip(): raise HTTPException(400, "عنوان الملزمة مطلوب")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".jpg", ".jpeg", ".png"}: raise HTTPException(400, "نوع الملف غير مدعوم")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    if not data: raise HTTPException(400, "الملف فارغ أو تعذر قراءته")
    if len(data) > 20 * 1024 * 1024: raise HTTPException(400, "حجم الملف أكبر من 20MB")
    stored = f"{uuid.uuid4().hex}{suffix}"; (UPLOAD_DIR / stored).write_bytes(data)
    c = db(); cur = c.execute("INSERT INTO files(title,file_name,stored_name,course_id,college,department,stage,section) VALUES(?,?,?,?,?,?,?,?)", (title.strip(), file.filename or stored, stored, course["id"], course["college"], course["department"], course["stage"], course["section"])); c.commit(); file_id = cur.lastrowid; c.close()
    notify_users("ملزمة / ملف جديد", title.strip(), course["college"], course["department"], course["stage"], course["section"])
    log_event("LECTURER_FILE_UPLOAD", u, None, f"رفع ملف لمادة {course['name']}: {title.strip()}")
    return {"id": file_id}

@app.post("/api/lecturer/announcements")
def lecturer_add_announcement(x: Announcement, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); course = lecturer_course(u)
    if not x.title.strip() or not x.body.strip():
        raise HTTPException(400, "عنوان الإعلان ونصه مطلوبان")
    c = db(); cur = c.execute("INSERT INTO announcements(title,body,college,department,stage,section) VALUES(?,?,?,?,?,?)",
        (x.title.strip(), x.body.strip(), course["college"], course["department"], course["stage"], course["section"])); c.commit(); aid=cur.lastrowid; c.close()
    notify_users(x.title, x.body, course["college"], course["department"], course["stage"], course["section"])
    log_event("LECTURER_ANNOUNCEMENT", u, None, f"{course['name']}: {x.title.strip()}")
    return {"id": aid}

@app.post("/api/admin/attendance")
def set_attendance(x: AttendanceUpdate, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True)
    if x.status not in {"حاضر", "غائب", "متأخر"}: raise HTTPException(400, "حالة الحضور غير صحيحة")
    c = db(); c.execute("INSERT INTO attendance(user_id,course_id,status,note,date) VALUES(?,?,?,?,CURRENT_DATE) ON CONFLICT(user_id,course_id,date) DO UPDATE SET status=excluded.status,note=excluded.note", (x.user_id, x.course_id, x.status, x.note)); c.commit(); c.close(); return {"ok": True}


@app.get("/api/files")
def list_files(authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db()
    if u["role"] == "admin": rows = c.execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    else: rows = c.execute("SELECT * FROM files WHERE college=? AND department=? AND (stage='' OR stage=?) AND (section=? OR section='ALL') ORDER BY id DESC", (u["college"], u["department"], u["stage"], u["section"])).fetchall()
    c.close(); return [{**dict(r), "download_url": f"/api/files/{r['id']}/download"} for r in rows]


@app.post("/api/admin/files")
async def upload_file(title: str = Form(...), college: str = Form(...), department: str = Form(...), stage: str = Form(...), section: str = Form("ALL"), file: UploadFile = File(...), authorization: Optional[str] = Header(default=None)):
    auth(authorization, True)
    validate_academic(college, department, "A", stage)
    if section != "ALL": validate_academic(college, department, section, stage)
    elif college not in COLLEGES or department not in COLLEGES[college]: raise HTTPException(400, "الكلية أو القسم غير صحيح")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".jpg", ".jpeg", ".png"}: raise HTTPException(400, "نوع الملف غير مدعوم")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024: raise HTTPException(400, "حجم الملف أكبر من 20MB")
    stored = f"{uuid.uuid4().hex}{suffix}"; (UPLOAD_DIR / stored).write_bytes(data)
    c = db(); cur = c.execute("INSERT INTO files(title,file_name,stored_name,college,department,stage,section) VALUES(?,?,?,?,?,?,?)", (title.strip(), file.filename or stored, stored, college, department, stage, section)); c.commit(); file_id = cur.lastrowid; c.close()
    notify_users("محاضرة / ملف جديد", title.strip(), college, department, stage, None if section == "ALL" else section); return {"id": file_id}


@app.get("/api/files/{file_id}/download")
def download_file(file_id: int, authorization: Optional[str] = Header(default=None)):
    u = auth(authorization); c = db(); row = c.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone(); c.close()
    if not row: raise HTTPException(404, "الملف غير موجود")
    if u["role"] != "admin" and (row["college"] != u["college"] or row["department"] != u["department"] or row["stage"] not in {"", u["stage"]} or row["section"] not in {"ALL", u["section"]}): raise HTTPException(403, "لا تملك صلاحية الوصول إلى هذا الملف")
    path = UPLOAD_DIR / row["stored_name"]
    if not path.exists(): raise HTTPException(404, "الملف غير موجود على الخادم")
    return FileResponse(path, filename=row["file_name"])


@app.delete("/api/admin/files/{file_id}")
def delete_file(file_id: int, authorization: Optional[str] = Header(default=None)):
    auth(authorization, True); c = db(); row = c.execute("SELECT stored_name FROM files WHERE id=?", (file_id,)).fetchone()
    if row:
        p = UPLOAD_DIR / row["stored_name"]
        if p.exists(): p.unlink(missing_ok=True)
    c.execute("DELETE FROM files WHERE id=?", (file_id,)); c.commit(); c.close(); return {"ok": True}
