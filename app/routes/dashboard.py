"""Serves the single-page web dashboard (app/static/dashboard)."""
import os

from flask import Blueprint, current_app, redirect, send_from_directory

bp = Blueprint('dashboard', __name__)

# Template previews render in a sandboxed srcdoc iframe and may load remote
# images, hence the relaxed img-src. Scripts only ever come from this origin.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src * data: blob:; frame-src 'self' about:; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def _index():
    directory = os.path.join(current_app.static_folder, 'dashboard')
    response = send_from_directory(directory, 'index.html', max_age=0)
    response.headers['Content-Security-Policy'] = CSP
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@bp.get('/')
def root():
    return redirect('/app/')


@bp.get('/app/')
def app_index():
    return _index()


@bp.get('/app')
def app_no_slash():
    return redirect('/app/')
