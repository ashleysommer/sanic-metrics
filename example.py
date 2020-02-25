from sanic import Sanic
from sanic.response import text
from spf import SanicPluginsFramework
from sanic_metrics import sanic_metrics

app = Sanic(__name__)
spf = SanicPluginsFramework(app)

metrics = spf.register_plugin(sanic_metrics, opt={'type': 'out'}, log={'format': 'vcombined'})

@app.route("/")
def index(request):
    return text("hello world")

if __name__ == "__main__":
    app.run("127.0.0.1", 8082, debug=True, auto_reload=False)
