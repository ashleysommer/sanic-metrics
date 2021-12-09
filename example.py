from sanic import Sanic
from sanic.response import text
from sanic_plugin_toolkit import SanicPluginRealm
from sanic_plugin_toolkit.plugins import contextualize
from sanic_metrics import sanic_metrics

app = Sanic(__name__)
realm = SanicPluginRealm(app)
ctx = realm.register_plugin(contextualize)
metrics = realm.register_plugin(sanic_metrics, opt={'type': 'out'}, log={'format': 'vcombined'})

@app.route("/")
def index(request):
    return text("hello world")

@ctx.route("/override")
async def orr(request, context):
    rctx = context.for_request(request)
    shared_ctx = context.shared
    shared_rctx = shared_ctx.for_request(request)
    override_metrics = {'status': "999"}
    shared_rctx['override_metrics'] = override_metrics
    return text("hello world")

if __name__ == "__main__":
    app.run("127.0.0.1", 8083, debug=True, auto_reload=False, access_log=False)
