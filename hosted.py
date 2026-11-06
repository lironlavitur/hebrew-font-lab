"""WSGI entry point for public hosting. No project state or uploads are saved."""
import json, logging
from pathlib import Path
from urllib.parse import urlsplit
from PIL import UnidentifiedImageError
import cv2
from core import process, make_font, decode, extract_cell, png, digitize_approved, validate_source_cell, source_issues

WEB = Path(__file__).parent / 'web'
MAX_BODY = 45_000_000
class RouteNotFound(Exception):
    pass
ALLOWED_FILES = {'/': ('index.html', 'text/html; charset=utf-8'), '/index.html': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}

def dispatch(path, data):
    if path == '/api/process': return process(data), False
    if path == '/api/digitize': return digitize_approved(data), False
    if path == '/api/validate-source': return validate_source_cell(decode(data['image'])), False
    if path == '/api/validate-set': return {'issues': source_issues(data['glyphs'])}, False
    if path == '/api/clean':
        check = validate_source_cell(decode(data.get('sourceOriginal') or data['image']))
        if not check['valid']: raise ValueError(check['error'])
        mask, warnings = extract_cell(decode(data['image']), int(data['threshold']))
        return {'mask': png(255-mask), 'warnings': warnings}, False
    if path == '/api/font':
        issues = source_issues(data['glyphs'])
        if issues: raise ValueError('האות '+issues[0]['char']+': '+issues[0]['error'])
        return make_font(data), True
    raise RouteNotFound('Not found')

def app(environ, start_response):
    def respond(code, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        headers = [('Content-Type', content_type), ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'same-origin'), ('X-Frame-Options', 'DENY')]
        if content_type == 'font/ttf': headers.append(('Content-Disposition', 'attachment; filename="MyHebrewFont.ttf"'))
        start_response(code, headers)
        return [body]
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')
    if path == '/health' and method == 'GET': return respond('200 OK', {'status': 'ok'})
    if method == 'GET':
        if path not in ALLOWED_FILES: return respond('404 Not Found', {'error': 'Not found'})
        filename, mime = ALLOWED_FILES[path]
        body = (WEB/filename).read_bytes()
        if filename == 'index.html':
            text = body.decode().replace('🔒 התמונות נשארות במחשב הזה', 'התמונות נשלחות לעיבוד בשרת ואינן נשמרות בו. שמרו פרויקט במחשב להמשך עבודה.')
            # Keep element IDs for local JS compatibility, but do not publish user samples.
            text = text.replace('id="openExample"', 'id="openExample" hidden disabled').replace('href="comparison.html"', 'href="#" hidden')
            body = text.encode()
        return respond('200 OK', body, mime)
    if method != 'POST': return respond('405 Method Not Allowed', {'error': 'Method not allowed'})
    # Cross-origin browser requests must not submit photos to this service.
    origin = environ.get('HTTP_ORIGIN')
    if origin and urlsplit(origin).netloc != environ.get('HTTP_HOST'):
        return respond('403 Forbidden', {'error': 'Origin not allowed'})
    if not environ.get('CONTENT_TYPE', '').lower().startswith('application/json'):
        return respond('415 Unsupported Media Type', {'error': 'נדרש קובץ נתונים בפורמט JSON'})
    try:
        length = int(environ.get('CONTENT_LENGTH') or 0)
        if length <= 0: return respond('400 Bad Request', {'error': 'חסרים נתוני הבקשה'})
        if length > MAX_BODY: return respond('413 Content Too Large', {'error': 'הקבצים גדולים מדי. הקטינו את הצילומים ונסו שוב.'})
        raw = environ['wsgi.input'].read(length)
        if len(raw) != length: raise ValueError('ההעלאה לא הושלמה')
        data = json.loads(raw)
        if not isinstance(data, dict): raise ValueError('נתוני הבקשה אינם תקינים')
        result, binary = dispatch(path, data)
        return respond('200 OK', result if binary else result, 'font/ttf' if binary else 'application/json; charset=utf-8')
    except RouteNotFound:
        return respond('404 Not Found', {'error': 'Not found'})
    except ValueError as error:
        return respond('400 Bad Request', {'error': str(error)})
    except (KeyError, TypeError, UnidentifiedImageError, cv2.error):
        return respond('400 Bad Request', {'error': 'לא ניתן לעבד את הנתונים. בדקו ששני הצילומים והפרויקט תקינים.'})
    except Exception:
        # No image bodies, filenames or student information are logged.
        logging.error('Font processing failed')
        return respond('500 Internal Server Error', {'error': 'העיבוד נכשל. נסו שוב או שמרו את הפרויקט ופנו למנחה.'})
