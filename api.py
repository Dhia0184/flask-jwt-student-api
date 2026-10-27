import os
from datetime import date

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_migrate import Migrate
from sqlalchemy import func, select
from werkzeug.exceptions import HTTPException

load_dotenv()

from auth import auth_required
from models import ROLE_ADMIN, ROLE_STUDENT, Report, Student, User, db  # noqa: E402

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///" + os.path.join(app.root_path, "students.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
migrate = Migrate(app, db)

REPORT_FIELDS = ["ID_S", "Title", "Type", "K1", "K2", "K3", "Release_Date"]
STUDENT_FIELDS = ["FN", "LN", "DMjr", "Level"]
MAX_REPORTS_PER_STUDENT = 2

# ----------------------------------------------------------------- errors
@app.errorhandler(HTTPException)
def handle_http_exception(error):
    response = error.get_response()
    response.set_data(app.json.dumps({"error": error.description}))
    response.content_type = "application/json"
    return response
 

@app.errorhandler(Exception)
def handle_unexpected_exception(error):
    app.logger.exception("Unhandled exception while processing request: %s", error)
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------- helpers
def json_body(required_fields):
    """Returns (data, None) or (None, error_response)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    missing = [f for f in required_fields if f not in data]
    if missing:
        return None, (jsonify({"error": f"Missing fields: {missing}"}), 400)
    return data, None


def clean_text(data, field, model, required):
    """Returns (error_message, cleaned_value). error_message is None if valid."""
    value = data[field]
    if not isinstance(value, str):
        return f"{field} must be a string", None
    value = value.strip()
    if required and not value:
        return f"{field} must be a non-empty string", None
    max_length = getattr(model, field).type.length
    if len(value) > max_length:
        return f"{field} must be at most {max_length} characters", None
    return None, value


def validate_student(data):
    """Returns (error_message, cleaned). cleaned is a dict ready to save."""
    cleaned = {}
    for field in ("FN", "LN"):
        error, value = clean_text(data, field, Student, required=True)
        if error:
            return error, None
        cleaned[field] = value
    if type(data["DMjr"]) is not bool:
        return "DMjr must be a boolean", None
    if type(data["Level"]) is not int or not 1 <= data["Level"] <= 4:
        return "Level must be an integer from 1 to 4", None
    cleaned["DMjr"] = data["DMjr"]
    cleaned["Level"] = data["Level"]
    return None, cleaned


def validate_report(data):
    """Returns (error_message, cleaned). cleaned is a dict ready to save."""
    if type(data["ID_S"]) is not int:
        return "ID_S must be an integer", None
    cleaned = {"ID_S": data["ID_S"]}
    for field in ("Title", "Type"):
        error, value = clean_text(data, field, Report, required=True)
        if error:
            return error, None
        cleaned[field] = value
    for field in ("K1", "K2", "K3"):
        error, value = clean_text(data, field, Report, required=False)
        if error:
            return error, None
        cleaned[field] = value
    try:
        cleaned["Release_Date"] = date.fromisoformat(data["Release_Date"])
    except (ValueError, TypeError):
        return "Release_Date must be a valid date in YYYY-MM-DD format", None
    return None, cleaned


def is_admin(user):
    return user.role == ROLE_ADMIN


def owns_student(user, student_id):
    return is_admin(user) or user.ID_S == student_id


def forbidden():
    return jsonify({"error": "You do not have permission to do this"}), 403


def paginated(model, order_column):
    """?page=1&limit=20 (limit capped at 100). Total count is in the X-Total-Count header."""
    page = max(request.args.get("page", 1, type=int), 1)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)
    total = db.session.scalar(select(func.count()).select_from(model))
    rows = db.session.scalars(
        select(model).order_by(order_column).limit(limit).offset((page - 1) * limit)
    ).all()
    response = jsonify([row.to_dict() for row in rows])
    response.headers["X-Total-Count"] = str(total)
    return response, 200


def commit_or_500(action):
    """Commit; on failure roll back and return an error response, else None."""
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to %s", action)
        return jsonify({"error": f"Failed to {action}"}), 500
    return None


# ------------------------------------------------------------------- auth
@app.route("/auth/me", methods=["GET"])
@auth_required()
def me():
    return jsonify(g.current_user.to_dict()), 200


# ---------------------------------------------------------------- reports
@app.route("/reports", methods=["GET"])
def get_all_reports():
    return paginated(Report, Report.ID_R)


@app.route("/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(report.to_dict()), 200


@app.route("/reports", methods=["POST"])
@auth_required()
def create_report():
    data, err = json_body(REPORT_FIELDS)
    if err:
        return err
    error, cleaned = validate_report(data)
    if error:
        return jsonify({"error": error}), 400

    if not owns_student(g.current_user, data["ID_S"]):
        return forbidden()

    student = db.session.get(Student, data["ID_S"])
    if student is None:
        return jsonify({"error": "Student not found"}), 404

    # NOTE: check-then-insert is not atomic; two simultaneous requests could both
    # pass. Fine here; a DB-level constraint/lock would fix it in production.
    if len(student.reports) >= MAX_REPORTS_PER_STUDENT:
        return jsonify({"error": "A student cannot have more than two reports"}), 400

    report = Report(**cleaned)
    db.session.add(report)
    if (err := commit_or_500("create report")) is not None:
        return err
    return jsonify(report.to_dict()), 201


@app.route("/reports/<int:report_id>", methods=["PUT"])
@auth_required()
def update_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        return jsonify({"error": "Report not found"}), 404
    if not owns_student(g.current_user, report.ID_S):
        return forbidden()

    data, err = json_body(REPORT_FIELDS)
    if err:
        return err
    if "ID_R" in data and data["ID_R"] != report_id:
        return jsonify({"error": "ID_R must match the report ID in the URL"}), 400
    error, cleaned = validate_report(data)
    if error:
        return jsonify({"error": error}), 400

    if data["ID_S"] != report.ID_S:
        if not is_admin(g.current_user):
            return forbidden()
        new_owner = db.session.get(Student, data["ID_S"])
        if new_owner is None:
            return jsonify({"error": "Student not found"}), 404
        if len(new_owner.reports) >= MAX_REPORTS_PER_STUDENT:
            return jsonify({"error": "A student cannot have more than two reports"}), 400

    for field, value in cleaned.items():
        setattr(report, field, value)

    if (err := commit_or_500("update report")) is not None:
        return err
    return jsonify(report.to_dict()), 200


@app.route("/reports/<int:report_id>", methods=["DELETE"])
@auth_required()
def delete_report(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        return jsonify({"error": "Report not found"}), 404
    if not owns_student(g.current_user, report.ID_S):
        return forbidden()

    db.session.delete(report)
    if (err := commit_or_500("delete report")) is not None:
        return err
    return jsonify({"message": "Report deleted"}), 200


# --------------------------------------------------------------- students
@app.route("/students", methods=["GET"])
@auth_required(ROLE_ADMIN)
def get_all_students():
    return paginated(Student, Student.ID_S)

@app.route("/students/count", methods=["GET"])
@auth_required(ROLE_ADMIN)
def get_student_count():
    """Returns the total number of students in the database."""
    total = db.session.scalar(select(func.count()).select_from(Student))
    return jsonify({"total_students": total}), 200


@app.route("/students/<int:student_id>", methods=["GET"])
@auth_required()
def get_student(student_id):
    if not owns_student(g.current_user, student_id):
        return forbidden()
    student = db.session.get(Student, student_id)
    if student is None:
        return jsonify({"error": "Student not found"}), 404
    return jsonify(student.to_dict()), 200


@app.route("/students", methods=["POST"])
@auth_required(ROLE_ADMIN)
def create_student():
    data, err = json_body(STUDENT_FIELDS)
    if err:
        return err
    error, cleaned = validate_student(data)
    if error:
        return jsonify({"error": error}), 400

    student = Student(**cleaned)
    db.session.add(student)
    if (err := commit_or_500("create student")) is not None:
        return err
    return jsonify(student.to_dict()), 201


@app.route("/students/<int:student_id>", methods=["PUT"])
@auth_required(ROLE_ADMIN)
def update_student(student_id):
    student = db.session.get(Student, student_id)
    if student is None:
        return jsonify({"error": "Student not found"}), 404

    data, err = json_body(STUDENT_FIELDS)
    if err:
        return err
    if "ID_S" in data and data["ID_S"] != student_id:
        return jsonify({"error": "ID_S must match the student ID in the URL"}), 400
    error, cleaned = validate_student(data)
    if error:
        return jsonify({"error": error}), 400

    for field, value in cleaned.items():
        setattr(student, field, value)
    if (err := commit_or_500("update student")) is not None:
        return err
    return jsonify(student.to_dict()), 200


@app.route("/students/<int:student_id>", methods=["DELETE"])
@auth_required(ROLE_ADMIN)
def delete_student(student_id):
    student = db.session.get(Student, student_id)
    if student is None:
        return jsonify({"error": "Student not found"}), 404

    # Unlink any login pointing at this student (their reports are deleted by cascade)
    for user in db.session.scalars(select(User).filter_by(ID_S=student_id)):
        user.ID_S = None
    db.session.delete(student)
    if (err := commit_or_500("delete student")) is not None:
        return err
    return jsonify({"message": "Student deleted"}), 200

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")