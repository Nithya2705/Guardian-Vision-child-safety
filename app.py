from flask import Flask, render_template, Response, redirect, request, session, jsonify
import cv2, os, math, sqlite3, smtplib,secrets
import uuid
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "guardianvision"

verify_tokens = {}

# ================= DATABASE =================
def get_db():
    return sqlite3.connect("users.db")

# ================= USERS =================
USERS = {
    "admin": {"password":"guardian123","role":"admin"},
    "security": {"password":"security123","role":"security"}
}

# ================= EMAIL =================
SENDER_EMAIL = "nithyashreemohan27@gmail.com"
APP_PASSWORD = "pymdcwsezohrcdbl"
GUARDIAN_EMAIL = "nithuchennai.m@gmail.com"
last_mail = {}
parent_last_mail = {}
# ================= AI =================
model = YOLO("yolov8m.pt")

# ================= CAMERAS (ADMIN) =================
CAMERA_FOLDERS = {
    "cam1":"videos/cam1",
    "cam2":"videos/cam2",
    "cam3":"videos/cam3",
    "cam4":"videos/cam4"
}

trackers = {cam: DeepSort(max_age=30) for cam in CAMERA_FOLDERS}
frame_index = {cam:0 for cam in CAMERA_FOLDERS}
stats = {cam:{"total":0,"safe":0,"danger":0} for cam in CAMERA_FOLDERS}
alert_log = {cam:[] for cam in CAMERA_FOLDERS}
ui_ids = {cam:{} for cam in CAMERA_FOLDERS}

# ================= PARENT VIDEO =================
UPLOAD_FOLDER = "videos/parent_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================= CHILD ID =================
def get_ui_id(cam, track_id):
    if track_id in ui_ids[cam]:
        return ui_ids[cam][track_id]
    ui_ids[cam][track_id] = len(ui_ids[cam]) + 1
    return ui_ids[cam][track_id]

# ================= EMAIL =================
def send_alert(cam, child, event):
    key=f"{cam}_{child}_{event}"
    if key in last_mail: return
    last_mail[key]=True

    msg=MIMEText(f"""
GuardianVision Alert 🚨
Camera: {cam}
Child: Child {child}
Event: {event}
Time: {datetime.now().strftime('%H:%M:%S')}
""")

    msg["Subject"]="⚠ Child Safety Alert"
    msg["From"]=SENDER_EMAIL
    msg["To"]=GUARDIAN_EMAIL

    try:
        server=smtplib.SMTP_SSL("smtp.gmail.com",465)
        server.login(SENDER_EMAIL,APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email error:",e)

# ================= FRAME =================
def get_frame(cam):
    files=sorted(os.listdir(CAMERA_FOLDERS[cam]))
    if not files: return None
    idx=frame_index[cam]
    frame=cv2.imread(os.path.join(CAMERA_FOLDERS[cam],files[idx]))
    frame_index[cam]=(idx+1)%len(files)
    return frame

# ================= PROCESS =================
def process_frame(frame, cam):
    h,w,_=frame.shape
    SAFE=(int(0.05*w),int(0.1*h),int(0.45*w),int(0.9*h))
    DANGER=(int(0.55*w),int(0.1*h),int(0.95*w),int(0.9*h))

    cv2.rectangle(frame,(SAFE[0],SAFE[1]),(SAFE[2],SAFE[3]),(0,255,0),2)
    cv2.rectangle(frame,(DANGER[0],DANGER[1]),(DANGER[2],DANGER[3]),(0,0,255),2)

    results=model(frame)[0]
    detections=[]
    for b in results.boxes:
        if int(b.cls[0])==0:
            x1,y1,x2,y2=map(int,b.xyxy[0])
            detections.append(([x1,y1,x2-x1,y2-y1],1.0,"child"))

    tracks=trackers[cam].update_tracks(detections,frame=frame)

    total=safe=danger=0
    for t in tracks:
        if not t.is_confirmed(): continue
        ui=get_ui_id(cam,t.track_id)

        l,tb,w2,h2=map(int,t.to_ltrb())
        cx,cy=l+w2//2,tb+h2//2
        total+=1

        in_danger=DANGER[0]<cx<DANGER[2] and DANGER[1]<cy<DANGER[3]
        color=(0,0,255) if in_danger else (0,255,0)

        if in_danger:
            danger+=1
            alert_log[cam].append({"time":datetime.now().strftime("%H:%M:%S"),"child":ui,"type":"Danger"})
            send_alert(cam,ui,"Danger")
        else:
            safe+=1

        cv2.rectangle(frame,(l,tb),(l+w2,tb+h2),color,2)
        cv2.putText(frame,f"Child {ui}",(l,tb-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,color,2)

    stats[cam]={"total":total,"safe":safe,"danger":danger}
    return frame

# ================= ADMIN STREAM =================
@app.route("/cctv")
def cctv():
    if session.get("role") != "admin" and session.get("role") != "security":
        return "Unauthorized", 403
    cam=request.args.get("cam","cam1")
    def gen():
        while True:
            f=get_frame(cam)
            if f is None: break
            f=process_frame(f,cam)
            _,buf=cv2.imencode(".jpg",f)
            yield(b"--frame\r\nContent-Type:image/jpeg\r\n\r\n"+buf.tobytes()+b"\r\n")
    return Response(gen(),mimetype="multipart/x-mixed-replace; boundary=frame")

# ================= PARENT STREAM =================

@app.route("/parent_ai")
def parent_ai():
    if session.get("role") != "parent":
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT status FROM users WHERE email=?", (session["email"],))
    status = cur.fetchone()[0]
    db.close()

    if status != "approved":
        return redirect("/parent_profile")

    return render_template("parent_ai.html")


parent_caps = {}   # each parent has their own video reader

@app.route("/parent_ai_upload", methods=["POST"])
def parent_ai_upload():
    if session.get("role") != "parent":
        return "Unauthorized", 403

    email = session["email"]
    folder = f"videos/parent_uploads/{email}"
    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, "video.mp4")
    request.files["video"].save(path)

    parent_caps[email] = cv2.VideoCapture(path)

    return "OK"


@app.route("/parent_ai_feed")
def parent_ai_feed():
    if session.get("role") != "parent":
        return "Unauthorized", 403

    email = session["email"]

    if email not in parent_caps:
        blank = cv2.imread("static/no_video.png")
        _,buf=cv2.imencode(".jpg",blank)
        return Response(
            b"--frame\r\nContent-Type:image/jpeg\r\n\r\n"+buf.tobytes()+b"\r\n",
            mimetype="multipart/x-mixed-replace; boundary=frame"
    )


    cap = parent_caps[email]

    def gen():
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            h,w,_ = frame.shape
            SAFE=(int(0.05*w),int(0.1*h),int(0.45*w),int(0.9*h))
            DANGER=(int(0.55*w),int(0.1*h),int(0.95*w),int(0.9*h))

            cv2.rectangle(frame,(SAFE[0],SAFE[1]),(SAFE[2],SAFE[3]),(0,255,0),2)
            cv2.rectangle(frame,(DANGER[0],DANGER[1]),(DANGER[2],DANGER[3]),(0,0,255),2)

            results = model(frame)[0]

            danger=False
            for b in results.boxes:
                if int(b.cls[0])==0:
                    x1,y1,x2,y2=map(int,b.xyxy[0])
                    cx=(x1+x2)//2
                    cy=(y1+y2)//2

                    in_danger = DANGER[0]<cx<DANGER[2] and DANGER[1]<cy<DANGER[3]
                    color=(0,0,255) if in_danger else (0,255,0)

                    if in_danger:
                        danger=True

                    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)

            if danger:
                send_parent_alert(email)

            _,buf=cv2.imencode(".jpg",frame)
            yield(b"--frame\r\nContent-Type:image/jpeg\r\n\r\n"+buf.tobytes()+b"\r\n")

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

def send_parent_alert(email):
    # ✅ prevent spam
    if email in parent_last_mail:
        return
    parent_last_mail[email] = True

    msg = MIMEText("Your child is in a danger zone.")
    msg["Subject"] = "GuardianVision Alert"
    msg["From"] = SENDER_EMAIL
    msg["To"] = email

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com",465)
        server.login(SENDER_EMAIL,APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except:
        pass


@app.route("/parent_upload",methods=["POST"])
def parent_upload():
    if session.get("role") != "parent":
        return "Unauthorized",403

    folder = os.path.join(UPLOAD_FOLDER, session["email"])
    os.makedirs(folder, exist_ok=True)

    request.files["video"].save(os.path.join(folder,"video.mp4"))

    # 🔹 Mark test video uploaded
    db = get_db()
    db.execute("UPDATE users SET test_video=1 WHERE email=?", (session["email"],))
    db.commit()
    db.close()

    return "OK"


@app.route("/parent_video")
def parent_video():
    if session.get("role")!="parent": return "Unauthorized",403
    path=os.path.join(UPLOAD_FOLDER,session["email"],"video.mp4")
    cap=cv2.VideoCapture(path)

    def gen():
        while True:
            ret,frame=cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES,0)
                continue
            results=model(frame)[0]
            for b in results.boxes:
                if int(b.cls[0])==0:
                    x1,y1,x2,y2=map(int,b.xyxy[0])
                    cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
            _,buf=cv2.imencode(".jpg",frame)
            yield(b"--frame\r\nContent-Type:image/jpeg\r\n\r\n"+buf.tobytes()+b"\r\n")
    return Response(gen(),mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/parent_profile")
def parent_profile():
    if session.get("role") != "parent":
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT name, email, child_name, status FROM users WHERE email=?",
        (session["email"],)
    )
    user = cur.fetchone()
    db.close()

    return render_template("parent_profile.html", user=user)



@app.route("/admin_parents")
def admin_parents():
    if session.get("role") != "admin":
        return "Unauthorized", 403

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM users WHERE status='pending'")
    pending = cur.fetchall()

    cur.execute("SELECT * FROM users WHERE status='approved'")
    approved = cur.fetchall()

    cur.execute("SELECT * FROM users WHERE status='rejected'")
    rejected = cur.fetchall()

    db.close()

    return render_template("admin_parents.html",
        pending=pending,
        approved=approved,
        rejected=rejected,
        msg=request.args.get("msg")
    )





# ================= API =================
@app.route("/stats")
def stats_api():
    return jsonify(stats[request.args.get("cam","cam1")])

@app.route("/alert_table")
def alert_table():
    cam=request.args.get("cam","cam1")
    return jsonify({"data":alert_log[cam][-50:]})

# ================= AUTH =================
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        try:
            name = request.form["name"]
            email = request.form["email"]
            password = request.form["password"]
            child = request.form["child"]
            age = request.form["child_age"]
            relation = request.form["relationship"]
            consent = request.form.get("consent")

            if not consent:
                return render_template("register.html", error="Consent is required")

            domain = email.split("@")[1]

            db = get_db()
            cur = db.cursor()

            cur.execute("""
                SELECT COUNT(*) FROM users
                WHERE email LIKE ? AND status='pending'
            """, (f"%@{domain}",))

            if cur.fetchone()[0] >= 3:
                db.close()
                return "❌ Too many pending accounts from this email domain today"

            # ✅ Insert user
            cur.execute("""
                INSERT INTO users
                (name,email,password,child_name,child_age,relationship,consent,status,email_verified)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                name, email, password, child,
                age, relation, 1,
                "pending", "no"
            ))

            db.commit()

            # ✅ Token save
            token = str(uuid.uuid4())
            cur.execute("UPDATE users SET verify_token=? WHERE email=?", (token, email))
            db.commit()

            verify_link = f"http://127.0.0.1:5000/verify/{token}"
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Verify your GuardianVision Email"
            msg["From"] = SENDER_EMAIL
            msg["To"] = email
            verify_link = f"http://127.0.0.1:5000/verify/{token}"
            html = f"""
            <html>
            <body>
            <h2>GuardianVision Email Verification</h2>
            <p>Hello {name},</p>
            <p>Click below to verify your email:</p>
            <a href="{verify_link}" 
            style="background:#00bcd4;color:white;padding:10px 20px;text-decoration:none;">
            Verify Email
            </a>
            <p>Or copy this link:</p>
            <p>{verify_link}</p>
            </body>
            </html>
            """ 
            part = MIMEText(html, "html")
            msg.attach(part)
            print("📨 Sending verification to:", email)
            try:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                server.login(SENDER_EMAIL, APP_PASSWORD)
                server.sendmail(SENDER_EMAIL, email, msg.as_string())  # ✅ IMPORTANT
                server.quit()
                print("✅ Verification mail sent")
            except Exception as e:
                print("❌ EMAIL ERROR:", e)
                db.close()
                return render_template("login.html",
                success="📧 Verification email sent")

        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email already registered!")

        except Exception as e:   # 🔥 THIS FIXES YOUR ERROR
            print("REGISTER ERROR:", e)
            return render_template("register.html", error="Something went wrong")

    # ✅ ALWAYS REQUIRED
    return render_template("register.html")

@app.route("/verify/<token>")
def verify(token):
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT email FROM users WHERE verify_token=?", (token,))
    row = cur.fetchone()

    if not row:
        db.close()
        return """
        <h2>❌ Verification link expired</h2>
        <p>This link is no longer valid.</p>
        <form action="/resend_verify_page" method="POST">
            <input name="email" placeholder="Enter your registered email" required>
            <button type="submit">Resend Verification</button>
        </form>
        """

    email = row[0]

    cur.execute("""
    UPDATE users 
    SET email_verified='yes', verify_token=NULL
    WHERE email=?
    """, (email,))
    db.commit()
    db.close()

    return "✅ Email verified successfully! You can now wait for admin approval."

@app.route("/resend_verify/<email>")
def resend_verify(email):
    token = str(uuid.uuid4())

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET verify_token=? WHERE email=?", (token, email))
    db.commit()
    db.close()

    link = f"http://127.0.0.1:5000/verify/{token}"

    msg = MIMEText(f"""
GuardianVision Email Verification

Your new verification link:
{link}

Please verify your email to continue.
""")

    msg["Subject"] = "GuardianVision – New Verification Link"
    msg["From"] = SENDER_EMAIL
    msg["To"] = email

    server = smtplib.SMTP_SSL("smtp.gmail.com",465)
    server.login(SENDER_EMAIL, APP_PASSWORD)
    server.send_message(msg)
    server.quit()

    return "📧 New verification link sent. Please check your email."

@app.route("/resend_verify_page", methods=["POST"])
def resend_verify_page():
    email = request.form["email"]

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    user = cur.fetchone()

    if not user:
        db.close()
        return "❌ Email not found"

    token = str(uuid.uuid4())
    cur.execute("UPDATE users SET verify_token=? WHERE email=?", (token, email))
    db.commit()
    db.close()

    link = f"http://127.0.0.1:5000/verify/{token}"

    msg = MIMEText(f"""
GuardianVision Email Verification

Click below to verify your email:
{link}
""")

    msg["Subject"] = "GuardianVision – New Verification Link"
    msg["From"] = SENDER_EMAIL
    msg["To"] = email

    server = smtplib.SMTP_SSL("smtp.gmail.com",465)
    server.login(SENDER_EMAIL, APP_PASSWORD)
    server.send_message(msg)
    server.quit()

    return "📧 New verification email sent. Check inbox."
@app.route("/approve/<int:uid>")
def approve(uid):
    if session.get("role") != "admin":
        return "Unauthorized", 403

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT email,email_verified FROM users WHERE id=?", (uid,))
    row = cur.fetchone()

    if not row:
        db.close()
        return "User not found"

    email, verified = row

    if verified != "yes":
        db.close()
        return "❌ Email not verified. Cannot approve."

    cur.execute("""
    UPDATE users 
    SET status='approved', reviewed_at=datetime('now'), rejection_reason=NULL
    WHERE id=?
    """, (uid,))
    db.commit()
    db.close()

    # Send approval email
    msg = MIMEText("""
🎉 Your GuardianVision account has been APPROVED!

You can now login and access live child monitoring.

Thank you for trusting GuardianVision.
""")
    msg["Subject"] = "GuardianVision – Account Approved"
    msg["From"] = SENDER_EMAIL
    msg["To"] = email

    server = smtplib.SMTP_SSL("smtp.gmail.com",465)
    server.login(SENDER_EMAIL,APP_PASSWORD)
    server.send_message(msg)
    server.quit()

    return redirect("/admin_parents?msg=approved")


@app.route("/reject/<int:uid>", methods=["POST"])
def reject(uid):
    if session.get("role") != "admin":
        return "Unauthorized", 403

    reason = request.form.get("reason","Not specified")

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT email FROM users WHERE id=?", (uid,))
    email = cur.fetchone()[0]

    cur.execute("""
    UPDATE users
    SET status='rejected',
        rejection_reason=?,
        reviewed_at=datetime('now')
    WHERE id=?
    """, (reason, uid))

    db.commit()
    db.close()

    msg = MIMEText(f"""
Your GuardianVision account has been REJECTED.

Reason:
{reason}

You may re-register with correct details.
""")

    msg["Subject"] = "GuardianVision – Account Rejected"
    msg["From"] = SENDER_EMAIL
    msg["To"] = email

    server = smtplib.SMTP_SSL("smtp.gmail.com",465)
    server.login(SENDER_EMAIL,APP_PASSWORD)
    server.send_message(msg)
    server.quit()

    return redirect("/admin_parents?msg=rejected")

@app.route("/delete_user/<int:uid>")
def delete_user(uid):
    if session.get("role") != "admin":
        return "Unauthorized", 403

    db = get_db()
    cur = db.cursor()

    # Get email for logging (optional)
    cur.execute("SELECT email FROM users WHERE id=?", (uid,))
    row = cur.fetchone()

    if not row:
        db.close()
        return "User not found"

    email = row[0]

    # Delete user
    cur.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    db.close()

    return redirect("/admin_parents")



@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")

        # ---------- ADMIN / SECURITY ----------
        if u in USERS and USERS[u]["password"] == p:
            session["user"] = u
            session["role"] = USERS[u]["role"]
            return jsonify({
                "success": True,
                "redirect": "/"
            })

        # ---------- PARENT ----------
        db = get_db()
        cur = db.cursor()

        cur.execute(
            "SELECT name, email, status, email_verified FROM users WHERE email=? AND password=?",
            (u, p)
        )
        row = cur.fetchone()   # 🔥 THIS LINE WAS MISSING

        db.close()

        # If user exists
        if row:
            # Email verification check
            if row[3] != "yes":
                return jsonify({
                    "success": False,
                    "message": "❌ Please verify your email first"
                })

            session["user"] = row[0]
            session["email"] = row[1]
            session["role"] = "parent"

            # redirect based on approval
            if row[2] == "approved":
                return jsonify({
                    "success": True,
                    "redirect": "/parent_ai"
                })
            else:
                return jsonify({
                    "success": True,
                    "redirect": "/parent_profile"
                })

        # ❌ If no user found
        return jsonify({
            "success": False,
            "message": "❌ Invalid username or password"
        })

    # ---------- GET ----------
    return render_template("login.html")


import uuid

reset_tokens = {}  # temporary memory store

@app.route("/forgot", methods=["GET","POST"])
def forgot():
    if request.method == "POST":
        email = request.form["email"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        db.close()

        if not user:
            return jsonify({"success":False})

        token = str(uuid.uuid4())
        reset_tokens[token] = email

        link = f"http://127.0.0.1:5000/reset/{token}"

        msg = MIMEText(f"""
GuardianVision Password Reset

Click the link below to reset your password:
{link}

If you did not request this, ignore.
""")

        msg["Subject"] = "GuardianVision Password Reset"
        msg["From"] = SENDER_EMAIL
        msg["To"] = email

        server = smtplib.SMTP_SSL("smtp.gmail.com",465)
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({"success":True})

    return render_template("forgot.html")
@app.route("/reset/<token>", methods=["GET","POST"])
def reset(token):
    if token not in reset_tokens:
        return "Invalid or expired link"

    if request.method=="POST":
        newpass=request.form["password"]
        email=reset_tokens[token]

        db=get_db()
        db.execute("UPDATE users SET password=? WHERE email=?", (newpass,email))
        db.commit()
        db.close()

        del reset_tokens[token]
        return redirect("/login")

    return render_template("reset.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
def index():
    if "user" not in session:
        return redirect("/login")
    if session["role"]=="admin":
        return render_template("index.html")
    if session["role"]=="security":
        return render_template("security.html")
    return redirect("/parent_ai")

app.run(debug=True)