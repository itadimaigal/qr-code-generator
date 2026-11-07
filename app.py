"""A tiny web page: paste a link, get a QR code.

    pip install flask
    python app.py        then open http://127.0.0.1:5000
"""
from flask import Flask, Response, render_template, request

import qrgen
from cli import check_link

app = Flask(__name__)


@app.route("/")
def home():
    link = request.args.get("link", "").strip()
    ec = request.args.get("ec", "M")
    if ec not in ("L", "M", "Q", "H"):
        ec = "M"
    svg = error = qr = None
    if link:
        try:
            link = check_link(link)
            qr = qrgen.make_qr(link, ec=ec)
            svg = qrgen.to_svg(qr, scale=8)
        except Exception as exc:
            error = str(exc)
    return render_template("index.html", link=link, ec=ec, svg=svg, qr=qr, error=error)


@app.route("/qr.png")
def qr_png():
    link = check_link(request.args["link"])
    ec = request.args.get("ec", "M")
    qr = qrgen.make_qr(link, ec=ec if ec in ("L", "M", "Q", "H") else "M")
    return Response(qrgen.to_png(qr, scale=12), mimetype="image/png",
                    headers={"Content-Disposition": "attachment; filename=qr-code.png"})


if __name__ == "__main__":
    app.run(debug=True)
