import math

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

OPERATIONS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


def parse_number(data, key):
    """Return the value as int/float, or None if it is not a finite number."""
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/calculate")
def calculate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Request body must be a JSON object."), 400

    operator = data.get("operator")
    if operator not in OPERATIONS:
        return jsonify(error="'operator' must be one of: +, -, *, /."), 400

    a = parse_number(data, "a")
    b = parse_number(data, "b")
    if a is None or b is None:
        return jsonify(error="'a' and 'b' must be finite numbers."), 400

    if operator == "/" and b == 0:
        return jsonify(error="Division by zero is not allowed."), 400

    result = OPERATIONS[operator](a, b)
    if isinstance(result, float) and not math.isfinite(result):
        return jsonify(error="Result is too large."), 400

    return jsonify(result=result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
