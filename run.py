from app import create_app

# The variable must be named `app` for gunicorn: `gunicorn run:app`
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
