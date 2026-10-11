from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///expense_sharing.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ----------------------------
# Database Models
# ----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    def __repr__(self):
        return f"<User {self.name}>"


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    paid_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    split_type = db.Column(db.String(20), nullable=False)  # equal/custom
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payer = db.relationship("User", backref="expenses_paid")


class ExpenseSplit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount_owed = db.Column(db.Float, nullable=False)

    expense = db.relationship("Expense", backref="splits")
    user = db.relationship("User", backref="expense_splits")


# ----------------------------
# Create DB
# ----------------------------
with app.app_context():
    db.create_all()


# ----------------------------
# Helper Functions
# ----------------------------
def calculate_balances():
    users = User.query.all()
    balances = {user.id: 0 for user in users}

    expenses = Expense.query.all()
    for expense in expenses:
        balances[expense.paid_by] += expense.total_amount
        for split in expense.splits:
            balances[split.user_id] -= split.amount_owed

    user_map = {user.id: user.name for user in users}
    summary = []
    for user_id, balance in balances.items():
        summary.append({
            "name": user_map[user_id],
            "balance": round(balance, 2)
        })
    return summary


# ----------------------------
# HTML Template
# ----------------------------
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Expense Sharing App</title>
    <style>
        body { font-family: Arial; margin: 40px; background: #f4f4f4; }
        h1, h2 { color: #333; }
        form, table { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        input, select, button { margin: 5px 0; padding: 8px; width: 100%%; }
        table { width: 100%%; border-collapse: collapse; }
        th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
        .row { display: flex; gap: 20px; }
        .col { flex: 1; }
    </style>
</head>
<body>
    <h1>Expense Sharing App</h1>

    <div class="row">
        <div class="col">
            <h2>Add User</h2>
            <form method="POST" action="/add_user">
                <input type="text" name="name" placeholder="Enter user name" required>
                <button type="submit">Add User</button>
            </form>
        </div>

        <div class="col">
            <h2>Add Expense</h2>
            <form method="POST" action="/add_expense">
                <input type="text" name="description" placeholder="Expense description" required>
                <input type="number" step="0.01" name="total_amount" placeholder="Total amount" required>

                <label>Payer:</label>
                <select name="paid_by" required>
                    {% for user in users %}
                        <option value="{{ user.id }}">{{ user.name }}</option>
                    {% endfor %}
                </select>

                <label>Participants (Ctrl+Click to select multiple):</label>
                <select name="participants" multiple required>
                    {% for user in users %}
                        <option value="{{ user.id }}">{{ user.name }}</option>
                    {% endfor %}
                </select>

                <label>Split Type:</label>
                <select name="split_type" required>
                    <option value="equal">Equal</option>
                    <option value="custom">Custom</option>
                </select>

                <input type="text" name="custom_amounts" placeholder="Custom amounts JSON, e.g. {&quot;1&quot;:50,&quot;2&quot;:100}">
                <button type="submit">Add Expense</button>
            </form>
        </div>
    </div>

    <h2>Expense History</h2>
    <table>
        <tr>
            <th>ID</th>
            <th>Description</th>
            <th>Total</th>
            <th>Paid By</th>
            <th>Split Type</th>
            <th>Date</th>
            <th>Splits</th>
        </tr>
        {% for expense in expenses %}
        <tr>
            <td>{{ expense.id }}</td>
            <td>{{ expense.description }}</td>
            <td>{{ expense.total_amount }}</td>
            <td>{{ expense.payer.name }}</td>
            <td>{{ expense.split_type }}</td>
            <td>{{ expense.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
            <td>
                {% for split in expense.splits %}
                    {{ split.user.name }}: {{ split.amount_owed }}<br>
                {% endfor %}
            </td>
        </tr>
        {% endfor %}
    </table>

    <h2>Balance Summary</h2>
    <table>
        <tr>
            <th>User</th>
            <th>Net Balance</th>
        </tr>
        {% for item in balances %}
        <tr>
            <td>{{ item.name }}</td>
            <td>
                {% if item.balance > 0 %}
                    Gets {{ item.balance }}
                {% elif item.balance < 0 %}
                    Owes {{ -item.balance }}
                {% else %}
                    Settled
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""


# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def index():
    users = User.query.all()
    expenses = Expense.query.order_by(Expense.created_at.desc()).all()
    balances = calculate_balances()
    return render_template_string(HTML, users=users, expenses=expenses, balances=balances)


@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form["name"].strip()
    if name:
        existing_user = User.query.filter_by(name=name).first()
        if not existing_user:
            user = User(name=name)
            db.session.add(user)
            db.session.commit()
    return redirect(url_for("index"))


@app.route("/add_expense", methods=["POST"])
def add_expense():
    description = request.form["description"].strip()
    total_amount = float(request.form["total_amount"])
    paid_by = int(request.form["paid_by"])
    split_type = request.form["split_type"]
    participants = request.form.getlist("participants")

    if not participants:
        return redirect(url_for("index"))

    expense = Expense(
        description=description,
        total_amount=total_amount,
        paid_by=paid_by,
        split_type=split_type
    )
    db.session.add(expense)
    db.session.commit()

    if split_type == "equal":
        split_amount = round(total_amount / len(participants), 2)
        for user_id in participants:
            split = ExpenseSplit(
                expense_id=expense.id,
                user_id=int(user_id),
                amount_owed=split_amount
            )
            db.session.add(split)

    elif split_type == "custom":
        custom_amounts_raw = request.form["custom_amounts"].strip()
        try:
            custom_amounts = json.loads(custom_amounts_raw)
            total_custom = sum(float(amount) for amount in custom_amounts.values())

            if round(total_custom, 2) == round(total_amount, 2):
                for user_id in participants:
                    if str(user_id) in custom_amounts:
                        split = ExpenseSplit(
                            expense_id=expense.id,
                            user_id=int(user_id),
                            amount_owed=float(custom_amounts[str(user_id)])
                        )
                        db.session.add(split)
        except Exception:
            db.session.delete(expense)
            db.session.commit()
            return redirect(url_for("index"))

    db.session.commit()
    return redirect(url_for("index"))


# ----------------------------
# Run App
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
