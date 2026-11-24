"""Conditional, authenticated fragments share the full page's calculation path."""
from hashlib import sha256
from flask import request, make_response, render_template

def live_template(template, **context):
    if not request.path.endswith('/fragment'):
        return render_template(template, **context)
    html = render_template(template.replace('.html', '_fragment.html'), **context)
    response = make_response(html)
    response.set_etag(sha256(html.encode()).hexdigest())
    response.headers['Cache-Control'] = 'private, no-cache'
    response.vary.add('Cookie')
    return response.make_conditional(request)
