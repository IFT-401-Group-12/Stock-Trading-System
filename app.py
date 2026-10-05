from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def customer_dashboard():
    return render_template("customer_dashboard.html")


@app.route("/stocks")
def stocks():
    return render_template("stocks.html")


@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")


@app.route("/transactions")
def transactions():
    return render_template("transaction_history.html")
    
@app.route("/login")
def login():
    return render_template("login.html")
    
@app.route("/signup")
def signup():
    return render_template("signup.html")


if __name__ == "__main__":
    app.run(debug=True)
    