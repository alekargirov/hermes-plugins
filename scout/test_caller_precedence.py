"""The precedence rule, exercised against the real function.

A live session user must ALWAYS beat SCOUT_USER_ID. If the env won, another
person talking to a shared bot would have their writes attributed to whoever
the env names — the exact confusion mission ownership exists to prevent.
"""
import importlib.util, os, sys, types

spec = importlib.util.spec_from_file_location('scout', '/p/scout/__init__.py')
scout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scout)

def with_session(value):
    """Install a fake gateway.session_context returning `value`."""
    for name in ('gateway', 'gateway.session_context'):
        sys.modules.pop(name, None)
    if value is None:
        return
    pkg = types.ModuleType('gateway')
    mod = types.ModuleType('gateway.session_context')
    mod.get_session_env = lambda k, d='': value if k == 'HERMES_SESSION_USER_ID' else d
    pkg.session_context = mod
    sys.modules['gateway'] = pkg
    sys.modules['gateway.session_context'] = mod

fails = []
def check(label, got, want):
    ok = got == want
    print(('  OK  ' if ok else '  FAIL') + f'  {label}: got {got!r} want {want!r}')
    if not ok: fails.append(label)

os.environ['SCOUT_USER_ID'] = '333700251'

with_session('999999999')
check('a live session user WINS over the env', scout._caller_telegram_id(), '999999999')

with_session('')
check('empty session falls back to the env', scout._caller_telegram_id(), '333700251')

with_session(None)  # no gateway module at all — cron in a bare process
check('no gateway module falls back to the env', scout._caller_telegram_id(), '333700251')

del os.environ['SCOUT_USER_ID']
with_session('')
check('neither configured nor talking -> empty', scout._caller_telegram_id(), '')

with_session('  333700251  ')
os.environ['SCOUT_USER_ID'] = 'x'
check('session id is trimmed', scout._caller_telegram_id(), '333700251')

sys.exit(1 if fails else 0)
