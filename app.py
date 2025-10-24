from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import datetime
from flask import send_file
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# ================= MySQL Connection =================
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="admin",
    database="smart_attendance"
)
cursor = db.cursor()

# ================= Upload Folder =================
UPLOAD_FOLDER = "static/uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ================= Create Faculty (for first-time setup) =================
@app.route('/create_faculty', methods=['GET', 'POST'])
def create_faculty():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO faculty (username, password_hash) VALUES (%s, %s)",
            (username, password_hash)
        )
        db.commit()
        flash(f"Faculty '{username}' created successfully!", "success")
        return redirect(url_for('login'))

    return render_template('create_faculty.html')


# ================= Faculty Login =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        password = request.form['password']

        cursor.execute("SELECT id, password_hash FROM faculty WHERE username=%s", (uname,))
        user = cursor.fetchone()

        if user and check_password_hash(user[1], password):
            session['faculty_id'] = user[0]
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')


# ================= Student Registration =================
@app.route('/register_student', methods=['GET', 'POST'])
def register_student():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        roll_no = request.form['roll_no']
        branch = request.form['branch']
        photo = request.files['photo']

        # Save photo with unique name
        filename = str(uuid.uuid4()) + "_" + photo.filename
        photo_path = os.path.join(UPLOAD_FOLDER, filename)
        photo.save(photo_path)

        # Insert student details
        cursor.execute(
            "INSERT INTO students (name, roll_no, branch, photo_path) VALUES (%s, %s, %s, %s)",
            (name, roll_no, branch, photo_path)
        )
        db.commit()
        flash("Student registered successfully!", "success")

    return render_template('register_student.html')


# ================= Mark Attendance =================
@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        cursor.execute("SELECT id, name, roll_no FROM students")
        students = cursor.fetchall()
        return render_template('mark_attendance.html', students=students)

    if request.method == 'POST':
        student_ids = request.form.getlist('present')
        today = datetime.date.today()
        now = datetime.datetime.now().strftime("%H:%M:%S")

        for student_id in student_ids:
            cursor.execute(
                "INSERT INTO attendance (student_id, date, time, status) VALUES (%s, %s, %s, %s)",
                (student_id, today, now, "Present")
            )
        db.commit()
        flash("Attendance marked successfully!", "success")
        return redirect(url_for('dashboard'))


# ================= Attendance Report =================
@app.route('/attendance_report')
def attendance_report():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("""
        SELECT s.name, s.roll_no, a.date, a.time, a.status, a.id
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.date DESC, a.time DESC
    """)
    records = cursor.fetchall()
    return render_template('report.html', records=records)


# ================= Delete Attendance Record =================
@app.route('/delete_attendance/<int:record_id>')
def delete_attendance(record_id):
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("DELETE FROM attendance WHERE id = %s", (record_id,))
    db.commit()
    flash("Attendance record deleted successfully!", "success")
    return redirect(url_for('attendance_report'))

# ================= Dashboard =================
@app.route('/dashboard')
def dashboard():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


# ================= Logout =================
@app.route('/logout')
def logout():
    session.pop('faculty_id', None)
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))
# ================= Homepage =================
@app.route('/')
def home():
    return render_template('home.html')  # <-- your homepage template



# ================= Delete All Attendance =================
@app.route('/delete_all_attendance')
def delete_all_attendance():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("DELETE FROM attendance")
    db.commit()
    flash("All attendance records deleted successfully!", "success")
    return redirect(url_for('attendance_report'))


# ================= Download Attendance as Excel =================
@app.route('/download_report_excel')
def download_report_excel():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("""
        SELECT s.name AS Name, s.roll_no AS RollNo, a.date AS Date, a.time AS Time, a.status AS Status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.date DESC, a.time DESC
    """)
    data = cursor.fetchall()
    df = pd.DataFrame(data, columns=['Name', 'Roll Number', 'Date', 'Time', 'Status'])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance Report')

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name='attendance_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ================= Download Attendance as PDF =================
@app.route('/download_report_pdf')
def download_report_pdf():
    if 'faculty_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("""
        SELECT s.name, s.roll_no, a.date, a.time, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.date DESC, a.time DESC
    """)
    records = cursor.fetchall()

    output = BytesIO()
    p = canvas.Canvas(output, pagesize=letter)
    width, height = letter

    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2, height - 50, "Attendance Report")
    p.setFont("Helvetica", 10)

    y = height - 80
    p.drawString(50, y, "Name")
    p.drawString(150, y, "Roll No")
    p.drawString(250, y, "Date")
    p.drawString(350, y, "Time")
    p.drawString(450, y, "Status")

    y -= 20
    for row in records:
        p.drawString(50, y, str(row[0]))
        p.drawString(150, y, str(row[1]))
        p.drawString(250, y, str(row[2]))
        p.drawString(350, y, str(row[3]))
        p.drawString(450, y, str(row[4]))
        y -= 20
        if y < 50:
            p.showPage()
            y = height - 80

    p.save()
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='attendance_report.pdf',
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    app.run(debug=True)