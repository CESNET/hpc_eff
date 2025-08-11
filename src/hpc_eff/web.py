from main import main
import io
from contextlib import redirect_stdout
from flask import Flask, render_template_string, request


f = io.StringIO()
with redirect_stdout(f):
    main()

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <title>HPC efficiency evaluator</title>
</head>
<body>
  <pre>{{ output }}</pre>

  <form method="post">
    <button type="submit">Run</button>
  </form>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    output = ""
    if request.method == "POST":
    	output = f.getvalue()
    return render_template_string(HTML, output=output)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


