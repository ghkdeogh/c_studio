"""Read-only Google OAuth for the local Studio; credentials never enter a project."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SCOPES = ('https://www.googleapis.com/auth/youtube.readonly',
          'https://www.googleapis.com/auth/yt-analytics.readonly')
LOCK = threading.RLock()
PENDING = {}


class GoogleError(ValueError):
    pass


def vault_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CreativeStudio' / 'youtube-oauth.bin'


def crypt(raw, decrypt=False):
    if os.name != 'nt':
        raise ValueError('인증 정보 암호화는 Windows 제작실에서 지원합니다.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = api.CryptUnprotectData if decrypt else api.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    fn.restype = ctypes.c_int
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Windows 인증 저장소를 열지 못했습니다. 같은 Windows 계정인지 확인해 주세요.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


def read_vault():
    path = vault_path()
    return json.loads(crypt(path.read_bytes(), True)) if path.exists() else {}


def save_vault(value):
    path = vault_path()
    raw = crypt(json.dumps(value).encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(secrets.token_hex(12) + '.tmp')
    tmp.write_bytes(raw)
    tmp.replace(path)


def status():
    with LOCK:
        try:
            value = read_vault()
            return {'configured': bool(value.get('client')), 'connected': bool(value.get('tokens')),
                    'channel': value.get('channel'), 'error': None}
        except (ValueError, OSError):
            return {'configured': False, 'connected': False, 'channel': None,
                    'error': '저장된 인증 정보를 읽을 수 없습니다. 연결 설정을 확인해 주세요.'}


def configure(document):
    client = document.get('installed') if isinstance(document, dict) else None
    if not isinstance(client, dict):
        raise ValueError('Google Cloud에서 데스크톱 앱 유형으로 받은 OAuth JSON을 선택해 주세요.')
    ident, secret = client.get('client_id'), client.get('client_secret')
    if (not isinstance(ident, str) or not ident.endswith('.apps.googleusercontent.com')
            or len(ident) > 300 or not isinstance(secret, str) or not 1 <= len(secret) <= 500):
        raise ValueError('OAuth 클라이언트 JSON 형식을 확인해 주세요.')
    with LOCK:
        old = read_vault()
        new = {'client_id': ident, 'client_secret': secret}
        if old.get('client') != new:
            # Explicit replacement of the client invalidates the previous connection.
            save_vault({'client': new})
            PENDING.clear()
    return status()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(endpoint, params=None, bearer=None, form=None):
    # Fixed endpoints only. Never send OAuth headers to user-supplied hosts.
    allowed = ('https://oauth2.googleapis.com/token',
               'https://www.googleapis.com/youtube/v3/channels',
               'https://www.googleapis.com/youtube/v3/videos',
               'https://youtubeanalytics.googleapis.com/v2/reports')
    if endpoint not in allowed:
        raise ValueError('지원하지 않는 Google API입니다.')
    url = endpoint + ('?' + urllib.parse.urlencode(params) if params else '')
    headers = {'Accept': 'application/json'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    raw = None
    if form is not None:
        raw = urllib.parse.urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=raw, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Google response/URL may contain tokens or identifiers; expose only known reasons.
        reason = ''
        try:
            error = json.loads(exc.read(100000)).get('error', {})
            reason = error if isinstance(error, str) else next(iter(error.get('errors', [])), {}).get('reason', '')
        except (ValueError, AttributeError, TypeError):
            pass
        if reason in ('invalid_grant', 'invalid_client') or exc.code == 401:
            raise GoogleError('Google 인증이 만료되었거나 설정이 다릅니다. Google 계정을 다시 연결해 주세요.') from None
        if reason in ('accessNotConfigured', 'serviceDisabled'):
            raise GoogleError('Google Cloud에서 YouTube Data API v3와 YouTube Analytics API를 사용 설정해 주세요.') from None
        if reason in ('quotaExceeded', 'dailyLimitExceeded') or exc.code == 429:
            raise GoogleError('Google API 사용량 한도에 도달했습니다. 나중에 다시 가져와 주세요.') from None
        raise GoogleError(f'Google API 요청을 완료하지 못했습니다(HTTP {exc.code}). 권한과 보고서 지원 여부를 확인해 주세요.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GoogleError('Google API 연결에 실패했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.') from None
    except ValueError:
        raise GoogleError('Google API 응답을 읽지 못했습니다. 다시 시도해 주세요.') from None


def start(port):
    with LOCK:
        value = read_vault()
        if not value.get('client'):
            raise ValueError('연결 설정에서 OAuth 클라이언트 JSON을 먼저 등록해 주세요.')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        redirect = f'http://127.0.0.1:{port}/api/youtube/oauth/callback'
        PENDING.clear()
        PENDING[state] = {'verifier': verifier, 'redirect': redirect, 'created': time.time(),
                          'client_id': value['client']['client_id']}
        query = {'client_id': value['client']['client_id'], 'redirect_uri': redirect,
                 'response_type': 'code', 'scope': ' '.join(SCOPES), 'state': state,
                 'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
                 'code_challenge_method': 'S256', 'access_type': 'offline', 'prompt': 'consent'}
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(query)
    if not webbrowser.open(url, new=2):
        raise ValueError('기본 브라우저를 열지 못했습니다. 기본 브라우저를 설정한 뒤 다시 연결해 주세요.')
    return {'ok': True, 'message': '기본 브라우저에서 Google 인증을 완료한 뒤 제작실로 돌아오세요.'}


def finish(params, port):
    with LOCK:
        pending = PENDING.pop(params.get('state', [''])[0], None)
        if not pending or time.time() - pending['created'] > 600 or pending['redirect'] != f'http://127.0.0.1:{port}/api/youtube/oauth/callback':
            raise ValueError('연결 요청이 만료되었거나 일치하지 않습니다. 제작실에서 다시 연결해 주세요.')
        if params.get('error'):
            raise ValueError('Google 연결이 취소되었습니다. 기존 성과 기록은 유지됩니다.')
        code = params.get('code', [''])[0]
        if not code or len(code) > 4096:
            raise ValueError('인증 코드가 없습니다. 다시 연결해 주세요.')
        value = read_vault()
        if value.get('client', {}).get('client_id') != pending['client_id']:
            raise ValueError('연결 설정이 변경되었습니다. 다시 시작해 주세요.')
        response = request_json('https://oauth2.googleapis.com/token', form={**value['client'],
            'code': code, 'code_verifier': pending['verifier'], 'redirect_uri': pending['redirect'],
            'grant_type': 'authorization_code'})
        if not set(SCOPES) <= set(response.get('scope', '').split()):
            raise ValueError('채널과 분석을 읽는 두 권한이 모두 필요합니다. 다시 연결해 주세요.')
        tokens = token_record(response)
        channels = request_json('https://www.googleapis.com/youtube/v3/channels',
                                {'part': 'snippet', 'mine': 'true'}, bearer=tokens['access_token'])
        items = channels.get('items', [])
        if len(items) != 1:
            raise ValueError('연결할 YouTube 채널 하나를 선택해 다시 인증해 주세요.')
        value.update(tokens=tokens, channel={'id': items[0]['id'], 'title': items[0]['snippet']['title']})
        save_vault(value)
    return status()


def token_record(response, old=None):
    if not isinstance(response.get('access_token'), str) or not response['access_token']:
        raise GoogleError('Google 인증 토큰을 받지 못했습니다. 다시 연결해 주세요.')
    return {'access_token': response['access_token'],
            'refresh_token': response.get('refresh_token', (old or {}).get('refresh_token')),
            'expires_at': time.time() + float(response.get('expires_in', 3600))}


def access():
    with LOCK:
        value = read_vault()
        tokens = value.get('tokens', {})
        if not tokens:
            raise ValueError('Google 계정을 먼저 연결해 주세요. Studio 화면 기록은 연결 없이 저장할 수 있습니다.')
        if tokens.get('expires_at', 0) < time.time() + 60:
            if not tokens.get('refresh_token'):
                raise ValueError('Google 계정을 다시 연결해 주세요.')
            response = request_json('https://oauth2.googleapis.com/token', form={**value['client'],
                'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token']})
            tokens = token_record(response, tokens)
            value['tokens'] = tokens
            save_vault(value)
        return tokens['access_token'], value['channel']
