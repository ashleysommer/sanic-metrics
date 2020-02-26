# -*- coding: utf-8 -*-
#
import time
from datetime import datetime, timedelta, timezone
from typing import List
from os import path
from spf import SanicPluginsFramework, SanicPlugin
from spf.context import SanicContext
from spf.plugin import PluginAssociated
from sanic import __version__ as sanic_version
from sanic.request import Request
from sanic.response import HTTPResponse, StreamingHTTPResponse
from .util import recursive_update, datetime_to_iso
from .version import __version__ as sanic_metrics_version

try:
    from sanic.compat import Header as MultiDict
except ImportError:
    from multidict import CIMultiDict as MultiDict

TRUTHS = {True, 1, 't', 'T', '1', "true", "TRUE", "True"}

class MetricsAssociated(PluginAssociated):
    pass



class SanicMetrics(SanicPlugin):

    AssociatedTuple = MetricsAssociated

    @classmethod
    def default_config(cls):
        return {
            'opt': {
                'type': 'in',
                'method': 'args',
                'key': 'metrics'
            },
            'log': {
                'format': 'common',  # common, combined, vcommon, vcombined, w3c
                'filename': 'access_{date:s}.txt'  # relative or absolute file path and file name
            },
            'save_headers': {  # save_headers can be False itself.
                'Host': True,
                'Referer': True,
                "User-Agent": True,
                "X-Forwarded-For": True,
                "X-Forwarded-Host": True
            },
            'save_cookies': False,
        }

    def on_registered(self, context, reg, *args, **kwargs):
        super(SanicMetrics, self).on_registered(context, reg, *args, **kwargs)
        config = self.default_config()
        recursive_update(config, kwargs)
        context.config = config

    @classmethod
    def collect_headers(cls, request, context):
        if request is None:
            return {}
        h = request.headers  # type: List[MultiDict]
        if h is None:
            return {}
        config = context.get('config', {})
        sh = config.get('save_headers', {})
        if sh is False:
            return {}
        ch = {}
        for header_name, do_save in sh.items():
            if not do_save:
                continue
            ch[header_name] = h.getall(header_name, [])
        return ch

    @classmethod
    def get_opt(cls, request, context):
        try:
            private_request_context = context.for_request(request)
            opt_choice = private_request_context.get('opt_choice', None)
            if opt_choice is not None:
                return opt_choice
        except (AttributeError, LookupError):
            private_request_context = None
        config = context.get('config', {})
        opt = config.get('opt', {})
        opt_type = opt.get('type', 'in')
        opt_method = opt.get('method', 'args')
        # opt_in = key and flag must be present using method to collect stats
        # opt_out = collect_status unless key and flag are present in stats
        if opt_method == "args":
            opt_key = opt.get("key", "metrics")
            val = request.args.getlist(opt_key, [None])[-1]
            if val is None:
                val = True if opt_type == "out" else False
            else:
                val = val in TRUTHS
        else:
            # opt_out method not implemented
            raise NotImplementedError("Opt-in method {}".format(opt_method))
        if opt_type == "out":
            opt_choice = False if val is False else True
        else:
            opt_choice = True if val is True else False
        if private_request_context is not None:
            private_request_context['opt_choice'] = opt_choice
        return opt_choice

    @classmethod
    def log_metrics(cls, metrics, context):
        config = context.get('config', {})
        log = config.get('log', {})
        if not log:
            return
        format = log.get('format', 'common').strip().lower()
        log_str = ""
        client = metrics.get('client', "0.0.0.0")
        method = metrics.get('method', 'GET')
        reqversion = metrics.get('reqversion', "1.0")
        nbytes = metrics.get('bytes', 0)
        status = metrics.get('status', 0)
        dt = metrics.get('datetime_start', datetime.now(tz=timezone.utc))
        host = metrics.get('host', "127.0.0.1")
        urlpath = metrics.get('path', '/')
        qs = metrics.get('qs')
        if format in ("common", "combined", "vcommon", "vcombined"):
            if format.startswith('v'):
                log_str += "{host:s}: ".format(host=host)
            client_rfc931 = metrics.get('client_rfc931', '-')
            client_username = metrics.get('client_username', '-')
            dt_string = dt.strftime("%d/%b/%Y:%H:%M:%S %z")
            p = ""+urlpath
            if qs:
                p += qs
            rq_string = "{m:s} {p:s} HTTP/{v:s}".format(m=method, p=p, v=reqversion)
            log_str += "{client:s} {rfc931:s} {username:s} [{dt:s}] \"{rq:s}\" {status:d} {nbytes:d}"\
                .format(client=client, username=client_username, rfc931=client_rfc931, dt=dt_string, rq=rq_string,
                        status=status, nbytes=nbytes)
            if format == "combined" or format == "vcombined":
                headers = metrics.get('headers', {})
                referrer = (headers.get('Referer', []) or [""])[-1]
                user_agent = (headers.get('User-Agent', []) or [""])[-1]
                cookies = metrics.get('cookies', None)
                if cookies is False or cookies is None:
                    log_str += " \"{ref:s}\" \"{ua:s}\"".format(ref=referrer, ua=user_agent)
                else:
                    log_str += " \"{ref:s}\" \"{ua:s}\" \"{cookie:s}\""\
                        .format(ref=referrer, ua=user_agent, cookie=cookies)
        elif format == "w3c":
            reqbytes = metrics.get('reqbytes', 0)
            headers = metrics.get('headers', {})
            time_taken = metrics.get('time_delta_ms', 0)
            referrer = (headers.get('Referer', []) or [""])[-1].replace(" ", "+")
            user_agent = (headers.get('User-Agent', []) or [""])[-1].replace(" ", "+")
            dt_string = dt.strftime("%Y-%m-%d %H:%M:%S")
            if qs is None:
                qs = ""
            #date time s-ip cs-method cs-uri-stem cs-uri-query cs-version cs-bytes c-ip cs(User-Agent) cs(Referrer) sc-status sc-version sc-bytes time-taken
            log_str += "{dt:s} {host:s} {method:s} {p:s} {qs:s} HTTP/{reqvers:s} {reqbytes:d} {client:s} {user_agent:s} {referrer:s} {status:d} HTTP/1.1 {nbytes:d} {time_taken:f}" \
                .format(dt=dt_string, host=host, method=method, p=urlpath, qs=qs, reqvers=reqversion, reqbytes=reqbytes, client=client,
                        user_agent=user_agent, referrer=referrer, status=status, nbytes=nbytes, time_taken=time_taken)
        else:
            raise NotImplementedError("Cannot log metrics for format {}".format(format))
        filename = log.get('filename', "access_{date:s}.txt")
        file_date = dt.strftime("%Y%m%d")
        filename = filename.format(date=file_date, host=host)
        if not path.exists(filename):
            cls.write_log_header(format, filename)
        with open(filename, "a+", encoding='utf-8') as f:
            f.write(log_str)
            f.write('\n')
        return

    @classmethod
    def write_log_header(cls, format, filename):
        if format in ("combined", "common", "vcombined", "vcommon"):
            return
        if format == "w3c":
            header = '''\
# Software: Sanic Web Server Framework {sanic_version:s} (Sanic-Metrics {sanic_metrics_version:s})
# Version: 1.0
# Date: {now_date:s}
# Fields: date time s-ip cs-method cs-uri-stem cs-uri-query cs-version cs-bytes c-ip cs(User-Agent) cs(Referrer) sc-status sc-version sc-bytes time-taken
'''
            # the fields are arranged to match the w3c log string parser in GoAccess log parser
            # "%d %t %^ %m %U %q %^ %^ %h %u %R %s %^ %^ %L",
            # date, time, skip, method, request, q, skip, skip, remote_host, useragent, referrer, status, skip, skip, time_taken_ms
            now_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            header = header.format(sanic_version=str(sanic_version), sanic_metrics_version=str(sanic_metrics_version),
                                   now_date=now_date)
        else:
            raise NotImplementedError("Cannot write logfile header for format {}".format(format))
        with open(filename, "w", encoding='utf-8') as f:
            f.write(header)
        return

    @classmethod
    def get_details_from_request(cls, request, context):
        details = {}
        try:
            host = request.server_name
        except:
            host = request.host
        try:
            remote_addr = request.remote_addr or request.ip
        except (AttributeError, LookupError):
            remote_addr = request.ip
        try:
            req_version = request.version
        except (AttributeError, LookupError):
            req_version = "1.0"
        headers = cls.collect_headers(request, context)
        path = request.path
        qs = request.query_string
        if qs:
            qs = "?{}".format(qs)
        else:
            qs = None
        try:
            body = request.body
            reqbytes = len(body)
            details['reqbytes'] = reqbytes
        except (AttributeError, LookupError):
            details['reqbytes'] = 0
        details['host'] = host
        details['reqversion'] = req_version
        details['method'] = request.method
        details['path'] = path
        details['qs'] = qs
        details['remote_addr'] = remote_addr
        details['headers'] = headers
        return details


sanic_metrics = instance = SanicMetrics()


@sanic_metrics.middleware(attach_to='request', relative='pre', priority=2, with_context=True)
def metrics_pre_req(request, context):
    """

    :param Request request:
    :param SanicContext context:
    :return:
    """
    time_pre = time.time()
    try:
        private_request_context = context.for_request(request)
    except (AttributeError, LookupError):
        # cannot get request context. Not on a valid request?
        return False
    if not sanic_metrics.get_opt(request, context):
        # opted out of metrics
        return False
    details = sanic_metrics.get_details_from_request(request, context)
    private_request_context.update(details)
    private_request_context['time_pre'] = time_pre
    return False


@sanic_metrics.middleware(attach_to='response', relative='post', priority=2, with_context=True)
def metrics_post_resp(request, response, context):
    """

    :param Request request:
    :param HTTPResponse response:
    :param SanicContext context:
    :return:
    """
    time_post = time.time()
    if not sanic_metrics.get_opt(request, context):
        # opted out of metrics
        return
    try:
        private_request_context = context.for_request(request)
        time_pre = private_request_context.get("time_pre", None)
    except (AttributeError, LookupError):
        # No request context. Must be a sanic 19.12+ route not-found error.
        # We can work around this
        private_request_context = sanic_metrics.get_details_from_request(request, context)
        time_pre = time_post
    if time_pre is None:
        # No time_pre? request_middleware probably didn't run, skip metrics
        return
    config = context.get('config', {})
    do_cookies = config.get('save_cookies', False)
    metrics = {}
    datetime_pre = datetime.fromtimestamp(time_pre, tz=timezone.utc)
    metrics["datetime_start"] = datetime_pre
    metrics["datetime_start_iso"] = datetime_to_iso(datetime_pre)
    if response:
        metrics['status'] = response.status
        try:
            resp_bytes = len(response.body)
        except (LookupError, AttributeError):
            resp_bytes = 0
        metrics['bytes'] = resp_bytes

        if do_cookies:
            metrics['cookies'] = ";".join("{:s}={:s}".format(k,v) for k,v in response.cookies.items())
        else:
            metrics['cookies'] = None
    else:
        metrics['status'] = 500
        metrics['bytes'] = 0
        metrics['cookies'] = None
    metrics['method'] = private_request_context.get('method', 'GET')
    metrics['reqbytes'] = private_request_context.get('reqbytes', 0)
    metrics['reqversion'] = private_request_context.get('reqversion', "1.0")
    metrics['path'] = private_request_context.get('path', "/")
    metrics['qs'] = private_request_context.get('qs', None)
    metrics['headers'] = private_request_context.get('headers', {})
    metrics['host'] = private_request_context.get('host', "127.0.0.1")
    metrics['client'] = private_request_context.get('remote_addr', "0.0.0.0")
    # Last thing, collect final time
    time_post = time.time()
    datetime_now = datetime.fromtimestamp(time_post, tz=timezone.utc)
    metrics["datetime_end"] = datetime_now
    metrics["datetime_end_iso"] = datetime_to_iso(datetime_now)
    time_delta_ms = (time_post - time_pre) * 1000.0
    metrics["time_delta_ms"] = time_delta_ms
    sanic_metrics.log_metrics(metrics, context)
    return False



