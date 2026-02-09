"""
Simple Flask Application for Testing
A basic calculator API with user management.
"""
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory storage
users = {}
calculations = []


# ==================== Calculator Functions ====================

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b. Raises ValueError if b is zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


# ==================== User Functions ====================

def create_user(username: str, email: str) -> dict:
    """Create a new user. Returns the user dict."""
    if not username or not email:
        raise ValueError("Username and email are required")
    if username in users:
        raise ValueError(f"User '{username}' already exists")
    if "@" not in email:
        raise ValueError("Invalid email format")
    
    user = {
        "username": username,
        "email": email,
        "active": True
    }
    users[username] = user
    return user


def get_user(username: str) -> dict | None:
    """Get a user by username. Returns None if not found."""
    return users.get(username)


def delete_user(username: str) -> bool:
    """Delete a user. Returns True if deleted, False if not found."""
    if username in users:
        del users[username]
        return True
    return False


def list_users() -> list[dict]:
    """List all users."""
    return list(users.values())


# ==================== API Routes ====================

@app.route("/")
def index():
    """Home endpoint."""
    return jsonify({"message": "Welcome to the Calculator API", "version": "1.0"})


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


@app.route("/calculate", methods=["POST"])
def calculate():
    """
    Perform a calculation.
    
    Request body:
        {"operation": "add|subtract|multiply|divide", "a": number, "b": number}
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    operation = data.get("operation")
    a = data.get("a")
    b = data.get("b")
    
    if operation is None or a is None or b is None:
        return jsonify({"error": "Missing required fields: operation, a, b"}), 400
    
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return jsonify({"error": "a and b must be numbers"}), 400
    
    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide
    }
    
    if operation not in operations:
        return jsonify({"error": f"Unknown operation: {operation}"}), 400
    
    try:
        result = operations[operation](a, b)
        calculations.append({"operation": operation, "a": a, "b": b, "result": result})
        return jsonify({"result": result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/users", methods=["GET", "POST"])
def users_endpoint():
    """List users or create a new user."""
    if request.method == "GET":
        return jsonify({"users": list_users()})
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    try:
        user = create_user(data.get("username"), data.get("email"))
        return jsonify({"user": user}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/users/<username>", methods=["GET", "DELETE"])
def user_endpoint(username):
    """Get or delete a specific user."""
    if request.method == "GET":
        user = get_user(username)
        if user:
            return jsonify({"user": user})
        return jsonify({"error": "User not found"}), 404
    
    if request.method == "DELETE":
        if delete_user(username):
            return jsonify({"message": f"User '{username}' deleted"})
        return jsonify({"error": "User not found"}), 404


@app.route("/history")
def history():
    """Get calculation history."""
    return jsonify({"calculations": calculations})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
