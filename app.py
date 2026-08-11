from flask import Flask

app = Flask(__name__)


@app.get("/")
def hello():
    return "Hello from CI/CD 2.0!\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
