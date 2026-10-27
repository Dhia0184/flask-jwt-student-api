from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"


class Student(db.Model):
    __tablename__ = "students"
    ID_S = db.Column(db.Integer, primary_key=True)
    FN = db.Column(db.String(50), nullable=False)
    LN = db.Column(db.String(50), nullable=False)
    DMjr = db.Column(db.Boolean, nullable=False)
    Level = db.Column(db.Integer, nullable=False)

    reports = db.relationship(
        "Report", backref="student", lazy=True, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "ID_S": self.ID_S,
            "FN": self.FN,
            "LN": self.LN,
            "DMjr": self.DMjr,
            "Level": self.Level,
        }


class Report(db.Model):
    __tablename__ = "reports"
    ID_R = db.Column(db.Integer, primary_key=True)
    ID_S = db.Column(db.Integer, db.ForeignKey("students.ID_S"), nullable=False)
    Title = db.Column(db.String(100), nullable=False)
    Type = db.Column(db.String(50), nullable=False)
    K1 = db.Column(db.String(50), nullable=False)
    K2 = db.Column(db.String(50), nullable=False)
    K3 = db.Column(db.String(50), nullable=False)
    Release_Date = db.Column(db.Date, nullable=False)

    def to_dict(self):
        return {
            "ID_R": self.ID_R,
            "ID_S": self.ID_S,
            "Title": self.Title,
            "Type": self.Type,
            "K1": self.K1,
            "K2": self.K2,
            "K3": self.K3,
            "Release_Date": self.Release_Date.isoformat() if self.Release_Date else None,
        }


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    keycloak_sub = db.Column(
    db.String(255),
    unique=True,
    nullable=True,
    index=True)

    role = db.Column(db.String(10), nullable=False, default=ROLE_STUDENT)
    # Links a login to a student record (lets a student read/edit only their own data)
    ID_S = db.Column(db.Integer, db.ForeignKey("students.ID_S"), nullable=True)

    def to_dict(self):
        return {"id": self.id, "username": self.username, "role": self.role, "ID_S": self.ID_S}
    