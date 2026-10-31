"""One short-lived native engine process, with a single JSON result protocol."""
import json
import sys
from wirelog_reasoning import build_result

if __name__ == '__main__':
    try:
        if '--probe' in sys.argv:
            from pyrewire import EasySession
            result = {'available': True}
        else:
            result = build_result()
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False), flush=True)
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False), flush=True)
        sys.exit(1)
